/**
 * GeoguessLayer — Imperative CesiumJS rendering of GeoGuessr game state.
 *
 * Renders:
 *   1. Agent guess pin (orange) at current_guess_lat/lon
 *   2. Actual location pin (green) revealed after round ends
 *   3. Error polyline from guess to actual (red, round-end only)
 *   4. Round history: faded grey pins for past rounds
 */
import { useEffect, useRef } from 'react';
import { useCesium } from 'resium';
import {
  Cartesian3,
  Color,
  NearFarScalar,
  LabelCollection,
  PointPrimitiveCollection,
  PolylineCollection,
  BlendOption,
  VerticalOrigin,
  Cartesian2 as CesiumCartesian2,
  LabelStyle,
} from 'cesium';
import * as Cesium from 'cesium';

import type { GeoGuessState } from '../../hooks/useGeoguess';

const LABEL_OFFSET = new CesiumCartesian2(0, -14);
const GUESS_COLOR = Color.fromCssColorString('#F97316');   // orange
const ACTUAL_COLOR = Color.fromCssColorString('#22C55E');  // green
const HISTORY_COLOR = Color.fromCssColorString('#6B7280'); // grey

interface Props {
  state: GeoGuessState | null;
  visible: boolean;
}

export default function GeoguessLayer({ state, visible }: Props) {
  const { viewer } = useCesium();
  const collectionsRef = useRef<{
    points: PointPrimitiveCollection;
    labels: LabelCollection;
    lines: PolylineCollection;
  } | null>(null);

  // Initialise collections once
  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const points = new PointPrimitiveCollection();
    const labels = new LabelCollection({ blendOption: BlendOption.TRANSLUCENT });
    const lines = new PolylineCollection();
    viewer.scene.primitives.add(lines);
    viewer.scene.primitives.add(points);
    viewer.scene.primitives.add(labels);
    collectionsRef.current = { points, labels, lines };
    return () => {
      try {
        if (!viewer.isDestroyed()) {
          viewer.scene.primitives.remove(lines);
          viewer.scene.primitives.remove(points);
          viewer.scene.primitives.remove(labels);
        }
      } catch { /* ok */ }
    };
  }, [viewer]);

  // Update on state change
  useEffect(() => {
    const cols = collectionsRef.current;
    if (!cols) return;

    cols.points.removeAll();
    cols.labels.removeAll();
    try { cols.lines.removeAll(); } catch { /* ok */ }

    cols.points.show = visible;
    cols.labels.show = visible;
    cols.lines.show = visible;

    if (!visible || !state) return;

    // ── Round history (faded grey) ────────────────────────────────────────────
    for (const rh of state.round_history) {
      if (rh.secret_lat != null) {
        const pos = Cartesian3.fromDegrees(rh.secret_lon, rh.secret_lat, 100);
        cols.points.add({ position: pos, color: HISTORY_COLOR.withAlpha(0.4), pixelSize: 8 });
        cols.labels.add({
          position: pos,
          text: `R${rh.round_number + 1} actual`,
          font: '9px monospace',
          fillColor: HISTORY_COLOR.withAlpha(0.5),
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: LABEL_OFFSET,
        });
      }
      if (rh.guess_lat != null && rh.guess_lon != null) {
        const gpos = Cartesian3.fromDegrees(rh.guess_lon, rh.guess_lat, 100);
        cols.points.add({ position: gpos, color: GUESS_COLOR.withAlpha(0.3), pixelSize: 6 });
        if (rh.secret_lat != null) {
          try {
            cols.lines.add({
              positions: [
                Cartesian3.fromDegrees(rh.guess_lon, rh.guess_lat, 100),
                Cartesian3.fromDegrees(rh.secret_lon, rh.secret_lat, 100),
              ],
              width: 1,
              material: Cesium.Material.fromType('Color', { color: HISTORY_COLOR.withAlpha(0.3) }),
            });
          } catch { /* ok */ }
        }
      }
    }

    // ── Current guess pin ─────────────────────────────────────────────────────
    if (state.current_guess_lat != null && state.current_guess_lon != null) {
      const gpos = Cartesian3.fromDegrees(state.current_guess_lon, state.current_guess_lat, 200);
      cols.points.add({
        position: gpos,
        color: GUESS_COLOR,
        pixelSize: 14,
        outlineColor: Color.WHITE,
        outlineWidth: 2,
        scaleByDistance: new NearFarScalar(1000, 1.5, 2e6, 0.5),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });
      cols.labels.add({
        position: gpos,
        text: 'GUESS',
        font: '11px monospace',
        fillColor: GUESS_COLOR,
        outlineColor: Color.BLACK,
        outlineWidth: 2,
        style: LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: VerticalOrigin.BOTTOM,
        pixelOffset: LABEL_OFFSET,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });
    }

    // ── Actual location (revealed after round ends) ───────────────────────────
    if (state.secret_lat != null && state.secret_lon != null) {
      const apos = Cartesian3.fromDegrees(state.secret_lon, state.secret_lat, 200);
      cols.points.add({
        position: apos,
        color: ACTUAL_COLOR,
        pixelSize: 14,
        outlineColor: Color.WHITE,
        outlineWidth: 2,
        scaleByDistance: new NearFarScalar(1000, 1.5, 2e6, 0.5),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });
      const label = state.secret_country !== '??'
        ? `ACTUAL\n${state.secret_country}, ${state.secret_region}`
        : 'ACTUAL';
      cols.labels.add({
        position: apos,
        text: label,
        font: '11px monospace',
        fillColor: ACTUAL_COLOR,
        outlineColor: Color.BLACK,
        outlineWidth: 2,
        style: LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: VerticalOrigin.BOTTOM,
        pixelOffset: LABEL_OFFSET,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      });

      // Error line: guess → actual
      if (state.current_guess_lat != null && state.current_guess_lon != null) {
        try {
          cols.lines.add({
            positions: [
              Cartesian3.fromDegrees(state.current_guess_lon, state.current_guess_lat, 200),
              Cartesian3.fromDegrees(state.secret_lon, state.secret_lat, 200),
            ],
            width: 2,
            material: Cesium.Material.fromType('Color', { color: Color.RED.withAlpha(0.7) }),
          });
        } catch { /* ok */ }
      }
    }

    try { if (!viewer?.isDestroyed()) viewer?.scene.requestRender(); } catch { /* ok */ }
  }, [state, visible, viewer]);

  return null;
}
