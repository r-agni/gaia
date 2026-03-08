import { useState, memo } from 'react';
import MobileModal from './MobileModal';

interface IntelFeedItem {
  id: string;
  time: string;
  type: 'battle' | 'system';
  message: string;
}

interface IntelFeedProps {
  items: IntelFeedItem[];
  isMobile?: boolean;
}

function IntelFeed({ items, isMobile = false }: IntelFeedProps) {
  const [visible, setVisible] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  const [bootMessages] = useState<IntelFeedItem[]>([
    {
      id: 'boot-1',
      time: new Date().toISOString().slice(11, 19),
      type: 'system',
      message: 'GAIA Battlefield System online',
    },
    {
      id: 'boot-2',
      time: new Date().toISOString().slice(11, 19),
      type: 'system',
      message: 'Cesium 3D engine loaded',
    },
    {
      id: 'boot-3',
      time: new Date().toISOString().slice(11, 19),
      type: 'system',
      message: 'Tactical display ready',
    },
  ]);

  const allItems = [...bootMessages, ...items].slice(-30);
  const liveCount = items.filter((i) => i.type !== 'system').length;

  const panelStyle: React.CSSProperties = {
    background: '#161b27',
    border: '1px solid #252d3d',
    borderLeft: '2px solid #E8A045',
    borderRadius: 4,
  };

  const feedList = (
    <div style={{ maxHeight: isMobile ? undefined : 280, overflowY: 'auto', padding: '6px 0' }}>
      {allItems.map((item) => (
        <div
          key={item.id}
          style={{
            display: 'flex',
            gap: 8,
            padding: '3px 12px',
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          <span style={{ color: '#2e3848', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
            {item.time}
          </span>
          <span
            style={{
              color: item.type === 'battle' ? '#D64045' : '#5a6478',
              flexShrink: 0,
              fontWeight: 600,
              minWidth: 28,
            }}
          >
            {item.type === 'battle' ? 'BTL' : 'SYS'}
          </span>
          <span style={{ color: '#d4dbe8' }}>{item.message}</span>
        </div>
      ))}
    </div>
  );

  if (isMobile) {
    return (
      <>
        <button
          onClick={() => setMobileOpen(true)}
          style={{
            position: 'fixed', top: 12, right: 12, zIndex: 40,
            width: 44, height: 44, borderRadius: 6,
            background: '#161b27', border: '1px solid #252d3d',
            borderLeft: '2px solid #E8A045',
            color: '#E8A045', fontSize: 16, cursor: 'pointer',
          }}
          aria-label="Open intel feed"
        >
          📡
          {liveCount > 0 && (
            <span style={{
              position: 'absolute', top: -4, right: -4,
              minWidth: 16, height: 16, borderRadius: '50%',
              background: '#E8A045', color: '#0f1117',
              fontSize: 9, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '0 2px',
            }}>
              {liveCount > 99 ? '99+' : liveCount}
            </span>
          )}
        </button>
        <MobileModal
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title="Combat Log"
          icon="📡"
          accent="bg-wv-amber"
        >
          {feedList}
        </MobileModal>
      </>
    );
  }

  return (
    <div style={{ position: 'fixed', bottom: 48, right: 16, width: 280, zIndex: 40, ...panelStyle }}>
      {/* Header */}
      <div
        style={{
          padding: '7px 12px',
          borderBottom: '1px solid #252d3d',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
        }}
        onClick={() => setVisible(!visible)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#E8A045', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Log
          </span>
          {liveCount > 0 && (
            <span style={{
              padding: '1px 5px', borderRadius: 3,
              background: '#E8A04520', color: '#E8A045',
              fontSize: 9, fontWeight: 700,
            }}>
              {liveCount}
            </span>
          )}
        </div>
        <span style={{ fontSize: 10, color: '#5a6478' }}>{visible ? '▲' : '▼'}</span>
      </div>

      {visible && feedList}
    </div>
  );
}

export default memo(IntelFeed);
export type { IntelFeedItem };
