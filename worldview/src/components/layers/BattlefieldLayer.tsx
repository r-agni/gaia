/**
 * BattlefieldLayer — Imperative CesiumJS rendering of battlefield units and objectives.
 *
 * Architecture mirrors ShipLayer: BillboardCollection + LabelCollection for units,
 * PointPrimitiveCollection for objectives. Dead-reckoning via preUpdate listener.
 */
import { useEffect, useRef } from 'react';
import { useCesium } from 'resium';
import {
  Cartesian3,
  Color,
  NearFarScalar,
  BillboardCollection,
  LabelCollection,
  PointPrimitiveCollection,
  BlendOption,
  VerticalOrigin,
  HorizontalOrigin,
  Cartesian2 as CesiumCartesian2,
  LabelStyle,
  Math as CesiumMath,
  Ellipsoid,
} from 'cesium';
import * as Cesium from 'cesium';

import type { BattlefieldState, BattlefieldUnit } from '../../hooks/useBattlefield';

const EllipsoidalOccluder = (Cesium as any).EllipsoidalOccluder as new (
  ellipsoid: typeof Ellipsoid.WGS84,
  cameraPosition: Cartesian3,
) => { isPointVisible(point: Cartesian3): boolean };

/* ─── constants ─────────────────────────────────────────────── */

const SIDE_COLORS: Record<string, string> = {
  attacker: '#FF4444',
  defender: '#4488FF',
};

const TYPE_SYMBOL: Record<string, string> = {
  infantry_squad: 'I',
  sniper_team: 'S',
  mortar_team: 'M',
  light_vehicle: 'V',
  armored_vehicle: 'A',
  helicopter: 'H',
  uav_drone: 'U',
  artillery_battery: '+',
  aa_emplacement: 'AA',
  fortified_position: 'F',
};

// Estimated speeds for dead-reckoning (kph converted to m/s)
const TYPE_SPEED_MPS: Record<string, number> = {
  infantry_squad: 5 / 3.6,
  sniper_team: 4 / 3.6,
  mortar_team: 3 / 3.6,
  light_vehicle: 60 / 3.6,
  armored_vehicle: 40 / 3.6,
  helicopter: 150 / 3.6,
  uav_drone: 100 / 3.6,
  artillery_battery: 0,
  aa_emplacement: 0,
  fortified_position: 0,
};

const FLYING_TYPES = new Set(['helicopter', 'uav_drone']);

function getUnitAltitude(u: BattlefieldUnit): number {
  return FLYING_TYPES.has(u.unit_type) ? 300 : 10;
}

const LABEL_OFFSET = new CesiumCartesian2(10, -4);

/* ─── unit icon canvas ──────────────────────────────────────── */

const _iconCache = new Map<string, HTMLCanvasElement>();

function createUnitIcon(side: string, symbol: string): HTMLCanvasElement {
  const key = `${side}:${symbol}`;
  if (_iconCache.has(key)) return _iconCache.get(key)!;

  const S = 48;
  const canvas = document.createElement('canvas');
  canvas.width = S;
  canvas.height = S;
  const c = canvas.getContext('2d')!;
  const cx = S / 2;
  const cy = S / 2;
  const r = 20;

  // Outer circle (colored by side)
  c.beginPath();
  c.arc(cx, cy, r, 0, Math.PI * 2);
  c.fillStyle = SIDE_COLORS[side] ?? '#FFFFFF';
  c.fill();

  // Dark ring
  c.beginPath();
  c.arc(cx, cy, r, 0, Math.PI * 2);
  c.strokeStyle = 'rgba(0,0,0,0.7)';
  c.lineWidth = 2;
  c.stroke();

  // Symbol text
  c.fillStyle = '#FFFFFF';
  c.font = `bold ${symbol.length > 1 ? 13 : 16}px monospace`;
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(symbol, cx, cy + 1);

  _iconCache.set(key, canvas);
  return canvas;
}

/* ═══════════════════════════════════════════════════════════════ */

export interface BattlefieldLayerProps {
  state: BattlefieldState | null;
  visible: boolean;
  isTracking: boolean;
}

export default function BattlefieldLayer({ state, visible, isTracking }: BattlefieldLayerProps) {
  const { viewer } = useCesium();

  const positionMapRef = useRef<Map<string, Cartesian3>>(new Map());
  const unitStateRef = useRef<Map<string, {
    lat: number; lon: number; alt: number;
    heading: number; speedMps: number;
    updatedAt: number;
  }>>(new Map());

  const collectionsRef = useRef<{
    billboards: BillboardCollection;
    labels: LabelCollection;
    objectives: PointPrimitiveCollection;
  } | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const primitiveMapRef = useRef<Map<string, { billboard: any; label: any }>>(new Map());
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const objPrimitiveMapRef = useRef<Map<string, any>>(new Map());

  /* ── Effect 1: Create / destroy primitive collections ── */
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const billboards = new BillboardCollection();
    const labels = new LabelCollection({ blendOption: BlendOption.TRANSLUCENT });
    const objectives = new PointPrimitiveCollection();

    viewer.scene.primitives.add(billboards);
    viewer.scene.primitives.add(labels);
    viewer.scene.primitives.add(objectives);

    collectionsRef.current = { billboards, labels, objectives };

    return () => {
      try {
        if (!viewer.isDestroyed()) {
          try { viewer.scene.primitives.remove(billboards); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(labels); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(objectives); } catch { /* ok */ }
        }
      } catch { /* viewer may be destroyed during HMR */ }
      collectionsRef.current = null;
      primitiveMapRef.current.clear();
      objPrimitiveMapRef.current.clear();
    };
  }, [viewer]);

  /* ── Effect 2: Sync battlefield state into primitives ── */
  useEffect(() => {
    const cols = collectionsRef.current;
    let viewerOk = false;
    try { viewerOk = !!viewer && !viewer.isDestroyed(); } catch { /* */ }
    if (!viewerOk || !cols) return;

    if (!visible || !state) {
      try {
        cols.billboards.removeAll();
        cols.labels.removeAll();
        cols.objectives.removeAll();
      } catch { /* destroyed */ }
      primitiveMapRef.current.clear();
      objPrimitiveMapRef.current.clear();
      positionMapRef.current.clear();
      unitStateRef.current.clear();
      return;
    }

    const activeIds = new Set<string>();

    // Sync units
    for (const u of state.units) {
      activeIds.add(u.unit_id);

      const alt = getUnitAltitude(u);
      const position = Cartesian3.fromDegrees(u.position.lon, u.position.lat, alt);
      const symbol = TYPE_SYMBOL[u.unit_type] ?? '?';
      const color = Color.fromCssColorString(SIDE_COLORS[u.side] ?? '#FFFFFF');
      const labelText = `${u.unit_id.slice(-3)} ${Math.round(u.health)}/${u.max_health}`;

      // Update dead-reckoning state
      unitStateRef.current.set(u.unit_id, {
        lat: u.position.lat,
        lon: u.position.lon,
        alt,
        heading: u.heading_deg,
        speedMps: TYPE_SPEED_MPS[u.unit_type] ?? 0,
        updatedAt: Date.now(),
      });
      positionMapRef.current.set(u.unit_id, position);

      const existing = primitiveMapRef.current.get(u.unit_id);
      if (existing) {
        existing.billboard.position = position;
        existing.billboard.color = color;
        existing.label.position = position;
        existing.label.text = labelText;
        existing.label.fillColor = color.withAlpha(0.9);
      } else {
        const billboard = cols.billboards.add({
          position,
          image: createUnitIcon(u.side, symbol),
          color,
          scale: 1.2,
          horizontalOrigin: HorizontalOrigin.CENTER,
          verticalOrigin: VerticalOrigin.CENTER,
          scaleByDistance: new NearFarScalar(1e3, 1.4, 2e6, 0.4),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        });
        const label = cols.labels.add({
          position,
          text: labelText,
          font: '11px monospace',
          fillColor: color.withAlpha(0.9),
          outlineColor: Color.BLACK,
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: LABEL_OFFSET,
          scaleByDistance: new NearFarScalar(1e3, 1.0, 5e5, 0),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        });
        primitiveMapRef.current.set(u.unit_id, { billboard, label });
      }
    }

    // Remove stale unit primitives
    for (const [id, prims] of primitiveMapRef.current) {
      if (!activeIds.has(id)) {
        try { cols.billboards.remove(prims.billboard); } catch { /* ok */ }
        try { cols.labels.remove(prims.label); } catch { /* ok */ }
        primitiveMapRef.current.delete(id);
        positionMapRef.current.delete(id);
        unitStateRef.current.delete(id);
      }
    }

    // Sync objectives
    const activeObjIds = new Set<string>();
    for (const obj of state.objectives) {
      activeObjIds.add(obj.objective_id);
      const pos = Cartesian3.fromDegrees(obj.position.lon, obj.position.lat, 5);

      // Color: gold if neutral, green if defender-controlled, red if attacker-controlled
      let objColor = Color.GOLD;
      if (obj.controlling_side === 'attacker') objColor = Color.fromCssColorString('#FF4444');
      else if (obj.controlling_side === 'defender') objColor = Color.fromCssColorString('#4488FF');

      const existingObj = objPrimitiveMapRef.current.get(obj.objective_id);
      if (existingObj) {
        existingObj.position = pos;
        existingObj.color = objColor;
      } else {
        const pt = cols.objectives.add({
          position: pos,
          color: objColor,
          pixelSize: 12,
          scaleByDistance: new NearFarScalar(1e4, 1.5, 5e6, 0.3),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        });
        objPrimitiveMapRef.current.set(obj.objective_id, pt);
      }
    }

    // Remove stale objective primitives
    for (const [id, pt] of objPrimitiveMapRef.current) {
      if (!activeObjIds.has(id)) {
        try { cols.objectives.remove(pt); } catch { /* ok */ }
        objPrimitiveMapRef.current.delete(id);
      }
    }
  }, [viewer, state, visible]);

  /* ── Effect 3: Visibility toggling ── */
  useEffect(() => {
    const cols = collectionsRef.current;
    if (!cols) return;
    cols.billboards.show = visible;
    cols.labels.show = visible && !isTracking;
    cols.objectives.show = visible;
  }, [visible, isTracking]);

  /* ── Effect 4: Dead-reckoning + occlusion via preUpdate ── */
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const BULK_MS = 500; // battlefield ticks are 1s+ so update more frequently
    let lastBulkUpdate = 0;

    const onPreUpdate = () => {
      try { if (viewer.isDestroyed()) return; } catch { return; }

      const now = Date.now();
      if (now - lastBulkUpdate < BULK_MS) return;
      lastBulkUpdate = now;

      const occluder = new EllipsoidalOccluder(Ellipsoid.WGS84, viewer.camera.positionWC);

      for (const [id, prims] of primitiveMapRef.current) {
        const st = unitStateRef.current.get(id);
        if (!st) continue;

        const dtSec = (now - st.updatedAt) / 1000;
        let lat = st.lat;
        let lon = st.lon;

        if (st.speedMps > 0 && dtSec > 0 && dtSec < 30) {
          const headRad = CesiumMath.toRadians(st.heading);
          lat += (Math.cos(headRad) * st.speedMps * dtSec) / 111320;
          const cosLat = Math.cos(lat * (Math.PI / 180)) || 0.0001;
          lon += (Math.sin(headRad) * st.speedMps * dtSec) / (111320 * cosLat);
        }

        const pos = Cartesian3.fromDegrees(lon, lat, st.alt);
        positionMapRef.current.set(id, pos);

        try {
          prims.billboard.position = pos;
          prims.label.position = pos;
          const vis = occluder.isPointVisible(pos);
          prims.billboard.show = vis;
          prims.label.show = vis;
        } catch { /* ok */ }
      }
    };

    viewer.scene.preUpdate.addEventListener(onPreUpdate);
    return () => {
      try {
        if (!viewer.isDestroyed()) {
          viewer.scene.preUpdate.removeEventListener(onPreUpdate);
        }
      } catch { /* ok */ }
    };
  }, [viewer]);

  return null;
}
