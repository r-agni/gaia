/**
 * BattlefieldLayer — Imperative CesiumJS rendering of battlefield units and objectives.
 *
 * Major visual features:
 * - NATO-style military icons (64px) with side-colored shapes per unit type
 * - Health bars rendered below each icon (green-to-red gradient)
 * - Pulsing objective rings with capture progress arcs
 * - Combat flash effect for units with active cooldowns
 * - Movement trails (fading polyline of last 5 positions)
 * - Detailed unit labels with type name, status, ammo
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

const SIDE_COLORS_LIGHT: Record<string, string> = {
  attacker: '#FF8888',
  defender: '#88AAFF',
};

const TYPE_NAMES: Record<string, string> = {
  infantry_squad: 'Infantry',
  sniper_team: 'Sniper',
  mortar_team: 'Mortar',
  light_vehicle: 'Light Veh',
  armored_vehicle: 'Armor',
  helicopter: 'Helo',
  uav_drone: 'UAV',
  artillery_battery: 'Artillery',
  aa_emplacement: 'AA',
  fortified_position: 'Fortified',
};

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

const ICON_SIZE = 64;
const LABEL_OFFSET = new CesiumCartesian2(12, -4);

/* ─── NATO icon canvas ─────────────────────────────────────── */

const _iconCache = new Map<string, HTMLCanvasElement>();

function hpColor(fraction: number): string {
  if (fraction > 0.6) return '#44FF44';
  if (fraction > 0.3) return '#FFCC00';
  return '#FF4444';
}

const HP_BUCKETS = 5; // 0%, 25%, 50%, 75%, 100% — fewer cache entries
function createUnitIcon(side: string, unitType: string, hpFraction: number, inCombat: boolean): HTMLCanvasElement {
  const hpBucket = Math.round(hpFraction * (HP_BUCKETS - 1)) / (HP_BUCKETS - 1);
  const key = `${side}:${unitType}:${hpBucket}:${inCombat ? 1 : 0}`;
  if (_iconCache.has(key)) return _iconCache.get(key)!;

  const S = ICON_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = S;
  canvas.height = S;
  const c = canvas.getContext('2d')!;
  const cx = S / 2;
  const cy = S / 2 - 4;

  const sideCol = SIDE_COLORS[side] ?? '#FFFFFF';

  // Combat glow effect
  if (inCombat) {
    c.save();
    c.shadowBlur = 16;
    c.shadowColor = sideCol;
    c.beginPath();
    c.arc(cx, cy, 26, 0, Math.PI * 2);
    c.fillStyle = sideCol + '30';
    c.fill();
    c.restore();
  }

  // Draw shape based on unit type (NATO-ish symbology)
  c.fillStyle = sideCol;
  c.strokeStyle = 'rgba(0,0,0,0.8)';
  c.lineWidth = 2;

  switch (unitType) {
    case 'infantry_squad': {
      // Filled rectangle
      c.fillRect(cx - 14, cy - 10, 28, 20);
      c.strokeRect(cx - 14, cy - 10, 28, 20);
      // X inside (infantry symbol)
      c.beginPath();
      c.moveTo(cx - 14, cy - 10); c.lineTo(cx + 14, cy + 10);
      c.moveTo(cx + 14, cy - 10); c.lineTo(cx - 14, cy + 10);
      c.strokeStyle = '#fff';
      c.lineWidth = 1.5;
      c.stroke();
      break;
    }
    case 'armored_vehicle': {
      // Diamond shape
      c.beginPath();
      c.moveTo(cx, cy - 16);
      c.lineTo(cx + 16, cy);
      c.lineTo(cx, cy + 16);
      c.lineTo(cx - 16, cy);
      c.closePath();
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      break;
    }
    case 'helicopter': {
      // Rotor-style: circle with blades
      c.beginPath();
      c.arc(cx, cy, 12, 0, Math.PI * 2);
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      // Rotor blades
      c.strokeStyle = sideCol;
      c.lineWidth = 2;
      c.beginPath();
      c.moveTo(cx - 18, cy); c.lineTo(cx + 18, cy);
      c.moveTo(cx, cy - 18); c.lineTo(cx, cy + 18);
      c.stroke();
      break;
    }
    case 'uav_drone': {
      // Delta/triangle shape
      c.beginPath();
      c.moveTo(cx, cy - 16);
      c.lineTo(cx + 14, cy + 12);
      c.lineTo(cx - 14, cy + 12);
      c.closePath();
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      break;
    }
    case 'sniper_team': {
      // Crosshair
      c.beginPath();
      c.arc(cx, cy, 12, 0, Math.PI * 2);
      c.strokeStyle = sideCol;
      c.lineWidth = 2;
      c.stroke();
      c.beginPath();
      c.moveTo(cx - 18, cy); c.lineTo(cx + 18, cy);
      c.moveTo(cx, cy - 18); c.lineTo(cx, cy + 18);
      c.strokeStyle = sideCol;
      c.lineWidth = 1.5;
      c.stroke();
      // Center dot
      c.beginPath();
      c.arc(cx, cy, 3, 0, Math.PI * 2);
      c.fillStyle = sideCol;
      c.fill();
      break;
    }
    case 'mortar_team': {
      // Arc symbol
      c.beginPath();
      c.arc(cx, cy + 6, 16, Math.PI, 0, false);
      c.fillStyle = sideCol;
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      // Base
      c.fillRect(cx - 6, cy + 4, 12, 8);
      break;
    }
    case 'artillery_battery': {
      // Circle with dot
      c.beginPath();
      c.arc(cx, cy, 14, 0, Math.PI * 2);
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      c.beginPath();
      c.arc(cx, cy, 4, 0, Math.PI * 2);
      c.fillStyle = '#fff';
      c.fill();
      break;
    }
    case 'aa_emplacement': {
      // Upward triangle
      c.beginPath();
      c.moveTo(cx, cy - 18);
      c.lineTo(cx + 16, cy + 12);
      c.lineTo(cx - 16, cy + 12);
      c.closePath();
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      // Inner upward arrow
      c.beginPath();
      c.moveTo(cx, cy - 8);
      c.lineTo(cx + 6, cy + 4);
      c.lineTo(cx - 6, cy + 4);
      c.closePath();
      c.fillStyle = '#fff';
      c.fill();
      break;
    }
    case 'fortified_position': {
      // Square with X
      c.fillRect(cx - 14, cy - 14, 28, 28);
      c.strokeRect(cx - 14, cy - 14, 28, 28);
      c.beginPath();
      c.moveTo(cx - 14, cy - 14); c.lineTo(cx + 14, cy + 14);
      c.moveTo(cx + 14, cy - 14); c.lineTo(cx - 14, cy + 14);
      c.strokeStyle = '#fff';
      c.lineWidth = 2;
      c.stroke();
      break;
    }
    default: {
      // Default: filled circle with letter
      c.beginPath();
      c.arc(cx, cy, 14, 0, Math.PI * 2);
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      c.fillStyle = '#fff';
      c.font = 'bold 14px monospace';
      c.textAlign = 'center';
      c.textBaseline = 'middle';
      c.fillText('?', cx, cy + 1);
      break;
    }
    case 'light_vehicle': {
      // Rounded rectangle (vehicle shape)
      const rr = 6;
      c.beginPath();
      c.moveTo(cx - 14 + rr, cy - 10);
      c.lineTo(cx + 14 - rr, cy - 10);
      c.quadraticCurveTo(cx + 14, cy - 10, cx + 14, cy - 10 + rr);
      c.lineTo(cx + 14, cy + 10 - rr);
      c.quadraticCurveTo(cx + 14, cy + 10, cx + 14 - rr, cy + 10);
      c.lineTo(cx - 14 + rr, cy + 10);
      c.quadraticCurveTo(cx - 14, cy + 10, cx - 14, cy + 10 - rr);
      c.lineTo(cx - 14, cy - 10 + rr);
      c.quadraticCurveTo(cx - 14, cy - 10, cx - 14 + rr, cy - 10);
      c.closePath();
      c.fill();
      c.strokeStyle = 'rgba(0,0,0,0.8)';
      c.stroke();
      // Wheel dots
      c.fillStyle = '#fff';
      c.beginPath(); c.arc(cx - 8, cy + 10, 3, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(cx + 8, cy + 10, 3, 0, Math.PI * 2); c.fill();
      break;
    }
  }

  // Health bar below icon (use bucketed value for consistency with cache key)
  const barW = 28;
  const barH = 4;
  const barX = cx - barW / 2;
  const barY = cy + 20;
  c.fillStyle = 'rgba(0,0,0,0.6)';
  c.fillRect(barX - 1, barY - 1, barW + 2, barH + 2);
  c.fillStyle = hpColor(hpBucket);
  c.fillRect(barX, barY, barW * Math.max(0, Math.min(1, hpBucket)), barH);

  _iconCache.set(key, canvas);
  return canvas;
}

/* ─── Objective ring canvas ──────────────────────────────── */

const _objIconCache = new Map<string, HTMLCanvasElement>();

function createObjectiveIcon(controlSide: string | null, captureProgress: number, tick: number): HTMLCanvasElement {
  const animFrame = Math.floor(tick / 2) % 4;
  const key = `obj:${controlSide}:${Math.round(captureProgress * 10)}:${animFrame}`;
  if (_objIconCache.has(key)) return _objIconCache.get(key)!;

  const S = 48;
  const canvas = document.createElement('canvas');
  canvas.width = S;
  canvas.height = S;
  const c = canvas.getContext('2d')!;
  const cx = S / 2;
  const cy = S / 2;

  let col = '#FFD700';
  if (controlSide === 'attacker') col = '#FF4444';
  else if (controlSide === 'defender') col = '#4488FF';

  // Pulsing outer ring
  const pulseR = 18 + (animFrame % 3);
  c.beginPath();
  c.arc(cx, cy, pulseR, 0, Math.PI * 2);
  c.strokeStyle = col + '60';
  c.lineWidth = 2;
  c.stroke();

  // Inner ring
  c.beginPath();
  c.arc(cx, cy, 12, 0, Math.PI * 2);
  c.strokeStyle = col;
  c.lineWidth = 2.5;
  c.stroke();

  // Capture progress arc fill
  if (captureProgress > 0) {
    c.beginPath();
    c.moveTo(cx, cy);
    c.arc(cx, cy, 10, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, captureProgress));
    c.closePath();
    c.fillStyle = col + '50';
    c.fill();
  }

  // Center dot
  c.beginPath();
  c.arc(cx, cy, 3, 0, Math.PI * 2);
  c.fillStyle = col;
  c.fill();

  _objIconCache.set(key, canvas);
  return canvas;
}

/* ═══════════════════════════════════════════════════════════════ */

export interface BattlefieldLayerProps {
  state: BattlefieldState | null;
  visible: boolean;
  isTracking: boolean;
}

const SYNC_INTERVAL_MS = 120;

export default function BattlefieldLayer({ state, visible, isTracking }: BattlefieldLayerProps) {
  const { viewer } = useCesium();

  const stateRef = useRef<BattlefieldState | null>(null);
  const visibleRef = useRef(visible);
  stateRef.current = state;
  visibleRef.current = visible;

  const positionMapRef = useRef<Map<string, Cartesian3>>(new Map());
  const trailMapRef = useRef<Map<string, { lat: number; lon: number }[]>>(new Map());
  const unitStateRef = useRef<Map<string, {
    lat: number; lon: number; alt: number;
    heading: number; speedMps: number;
    updatedAt: number;
  }>>(new Map());

  const collectionsRef = useRef<{
    billboards: BillboardCollection;
    labels: LabelCollection;
    objBillboards: BillboardCollection;
    objLabels: LabelCollection;
    combatPoints: PointPrimitiveCollection;
  } | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const primitiveMapRef = useRef<Map<string, { billboard: any; label: any }>>(new Map());
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const objPrimitiveMapRef = useRef<Map<string, { billboard: any; label: any }>>(new Map());

  /* ── Effect 1: Create / destroy primitive collections ── */
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const billboards = new BillboardCollection();
    const labels = new LabelCollection({ blendOption: BlendOption.TRANSLUCENT });
    const objBillboards = new BillboardCollection();
    const objLabels = new LabelCollection({ blendOption: BlendOption.TRANSLUCENT });
    const combatPoints = new PointPrimitiveCollection();

    viewer.scene.primitives.add(billboards);
    viewer.scene.primitives.add(labels);
    viewer.scene.primitives.add(objBillboards);
    viewer.scene.primitives.add(objLabels);
    viewer.scene.primitives.add(combatPoints);

    collectionsRef.current = { billboards, labels, objBillboards, objLabels, combatPoints };

    return () => {
      try {
        if (!viewer.isDestroyed()) {
          try { viewer.scene.primitives.remove(billboards); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(labels); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(objBillboards); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(objLabels); } catch { /* ok */ }
          try { viewer.scene.primitives.remove(combatPoints); } catch { /* ok */ }
        }
      } catch { /* viewer may be destroyed during HMR */ }
      collectionsRef.current = null;
      primitiveMapRef.current.clear();
      objPrimitiveMapRef.current.clear();
    };
  }, [viewer]);

  /* ── Effect 2: Clear when hidden or no state; refs updated at top of component ── */
  useEffect(() => {
    const cols = collectionsRef.current;
    let viewerOk = false;
    try { viewerOk = !!viewer && !viewer.isDestroyed(); } catch { /* */ }
    if (!viewerOk || !cols) return;

    if (!visible || !state) {
      try {
        cols.billboards.removeAll();
        cols.labels.removeAll();
        cols.objBillboards.removeAll();
        cols.objLabels.removeAll();
        cols.combatPoints.removeAll();
      } catch { /* destroyed */ }
      primitiveMapRef.current.clear();
      objPrimitiveMapRef.current.clear();
      positionMapRef.current.clear();
      unitStateRef.current.clear();
      trailMapRef.current.clear();
      return;
    }
  }, [viewer, state, visible]);

  /* ── Effect 2b: Throttled sync of state to Cesium (runs at fixed interval) ── */
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const cols = collectionsRef.current;
    if (!cols) return;

    const tick = () => {
      const state = stateRef.current;
      if (!state || !visibleRef.current) return;
      try {
        if (viewer.isDestroyed()) return;
      } catch {
        return;
      }
      const c = collectionsRef.current;
      if (!c) return;

      const activeIds = new Set<string>();
      const stateTick = state.tick;

      try {
        c.combatPoints.removeAll();
      } catch { /* ok */ }

      for (const u of state.units) {
        activeIds.add(u.unit_id);

        const alt = getUnitAltitude(u);
        const position = Cartesian3.fromDegrees(u.position.lon, u.position.lat, alt);
        const hpFrac = u.max_health > 0 ? u.health / u.max_health : 0;
        const inCombat = (u.cooldown_ticks_remaining ?? 0) > 0;
        const typeName = TYPE_NAMES[u.unit_type] ?? u.unit_type;

        let statusText = '';
        if (u.status === 'destroyed') statusText = ' [DEAD]';
        else if (u.dug_in) statusText = ' [DUG IN]';
        else if (u.status === 'retreating') statusText = ' [RETREAT]';

        const labelText = `${typeName}${statusText}\n${Math.round(u.health)}/${u.max_health} HP`;

        const trail = trailMapRef.current.get(u.unit_id) ?? [];
        const lastPos = trail[trail.length - 1];
        if (!lastPos || lastPos.lat !== u.position.lat || lastPos.lon !== u.position.lon) {
          trail.push({ lat: u.position.lat, lon: u.position.lon });
          if (trail.length > 5) trail.shift();
          trailMapRef.current.set(u.unit_id, trail);
        }

        unitStateRef.current.set(u.unit_id, {
          lat: u.position.lat,
          lon: u.position.lon,
          alt,
          heading: u.heading_deg,
          speedMps: TYPE_SPEED_MPS[u.unit_type] ?? 0,
          updatedAt: Date.now(),
        });
        positionMapRef.current.set(u.unit_id, position);

        const sideColor = Color.fromCssColorString(SIDE_COLORS[u.side] ?? '#FFFFFF');
        const labelColor = Color.fromCssColorString(SIDE_COLORS_LIGHT[u.side] ?? '#FFFFFF');

        const existing = primitiveMapRef.current.get(u.unit_id);
        if (existing) {
          existing.billboard.position = position;
          existing.billboard.image = createUnitIcon(u.side, u.unit_type, hpFrac, inCombat);
          existing.label.position = position;
          existing.label.text = labelText;
          existing.label.fillColor = labelColor.withAlpha(0.9);
        } else {
          const billboard = c.billboards.add({
            position,
            image: createUnitIcon(u.side, u.unit_type, hpFrac, inCombat),
            color: Color.WHITE,
            scale: 1.0,
            horizontalOrigin: HorizontalOrigin.CENTER,
            verticalOrigin: VerticalOrigin.CENTER,
            scaleByDistance: new NearFarScalar(500, 1.6, 2e6, 0.3),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
          const label = c.labels.add({
            position,
            text: labelText,
            font: '11px monospace',
            fillColor: labelColor.withAlpha(0.9),
            outlineColor: Color.BLACK,
            outlineWidth: 3,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: LABEL_OFFSET,
            scaleByDistance: new NearFarScalar(500, 1.0, 5e5, 0),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
          primitiveMapRef.current.set(u.unit_id, { billboard, label });
        }

        if (inCombat) {
          c.combatPoints.add({
            position,
            color: sideColor.withAlpha(0.6),
            pixelSize: 24,
            scaleByDistance: new NearFarScalar(500, 2.0, 5e5, 0.2),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
        }
      }

      for (const [id, prims] of primitiveMapRef.current) {
        if (!activeIds.has(id)) {
          try { c.billboards.remove(prims.billboard); } catch { /* ok */ }
          try { c.labels.remove(prims.label); } catch { /* ok */ }
          primitiveMapRef.current.delete(id);
          positionMapRef.current.delete(id);
          unitStateRef.current.delete(id);
          trailMapRef.current.delete(id);
        }
      }

      const activeObjIds = new Set<string>();
      for (const obj of state.objectives) {
        activeObjIds.add(obj.objective_id);
        const pos = Cartesian3.fromDegrees(obj.position.lon, obj.position.lat, 5);
        const objImage = createObjectiveIcon(obj.controlling_side, obj.capture_progress, stateTick);

        let objColor = Color.GOLD;
        if (obj.controlling_side === 'attacker') objColor = Color.fromCssColorString('#FF4444');
        else if (obj.controlling_side === 'defender') objColor = Color.fromCssColorString('#4488FF');

        const existingObj = objPrimitiveMapRef.current.get(obj.objective_id);
        if (existingObj) {
          existingObj.billboard.position = pos;
          existingObj.billboard.image = objImage;
          existingObj.label.position = pos;
          existingObj.label.text = obj.name || obj.objective_id;
          existingObj.label.fillColor = objColor.withAlpha(0.9);
        } else {
          const billboard = c.objBillboards.add({
            position: pos,
            image: objImage,
            color: Color.WHITE,
            scale: 1.0,
            horizontalOrigin: HorizontalOrigin.CENTER,
            verticalOrigin: VerticalOrigin.CENTER,
            scaleByDistance: new NearFarScalar(1e3, 1.8, 5e6, 0.4),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
          const label = c.objLabels.add({
            position: pos,
            text: obj.name || obj.objective_id,
            font: 'bold 12px monospace',
            fillColor: objColor.withAlpha(0.9),
            outlineColor: Color.BLACK,
            outlineWidth: 3,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.TOP,
            pixelOffset: new CesiumCartesian2(0, 26),
            scaleByDistance: new NearFarScalar(1e3, 1.0, 5e5, 0),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
          objPrimitiveMapRef.current.set(obj.objective_id, { billboard, label });
        }
      }

      for (const [id, prims] of objPrimitiveMapRef.current) {
        if (!activeObjIds.has(id)) {
          try { c.objBillboards.remove(prims.billboard); } catch { /* ok */ }
          try { c.objLabels.remove(prims.label); } catch { /* ok */ }
          objPrimitiveMapRef.current.delete(id);
        }
      }

      // requestRenderMode=true means Cesium won't redraw unless asked explicitly.
      // Force a render now that primitives have been mutated.
      try { if (!viewer.isDestroyed()) viewer.scene.requestRender(); } catch { /* ok */ }
    };

    const id = setInterval(tick, SYNC_INTERVAL_MS);
    tick(); // run once immediately when state is available
    return () => clearInterval(id);
  }, [viewer]);

  /* ── Effect 3: Visibility toggling ── */
  useEffect(() => {
    const cols = collectionsRef.current;
    if (!cols) return;
    cols.billboards.show = visible;
    cols.labels.show = visible && !isTracking;
    cols.objBillboards.show = visible;
    cols.objLabels.show = visible;
    cols.combatPoints.show = visible;
  }, [visible, isTracking]);

  /* ── Effect 4: Dead-reckoning + occlusion via preUpdate ── */
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const BULK_MS = 900;
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

      // Request a render so dead-reckoning positions are visible.
      try { if (!viewer.isDestroyed()) viewer.scene.requestRender(); } catch { /* ok */ }
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
