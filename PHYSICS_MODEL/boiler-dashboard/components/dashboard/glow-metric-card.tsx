import { ResponsiveContainer, AreaChart, Area, CartesianGrid, YAxis, Tooltip } from 'recharts';

export function GlowMetricCard({ title, value, unit, data, dataKey, color, colorEnd, icon: Icon, glowColor }: any) {
  const values = data.map((d: any) => d[dataKey]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // Give slightly more padding to allow the chart to breathe
  const padding = (max - min) * 0.6;
  const gradId = `glow-grad-${dataKey}`;
  const filterId = `glow-filter-${dataKey}`;
  const strokeGradId = `stroke-grad-${dataKey}`;

  return (
    <div className="group" style={{
      position: 'relative', overflow: 'hidden', height: '360px',
      display: 'flex', flexDirection: 'column',
      background: 'linear-gradient(165deg, rgba(30, 30, 33, 0.6) 0%, rgba(18, 18, 20, 0.7) 50%, rgba(5, 5, 8, 0.9) 100%)',
      backdropFilter: 'blur(20px)',
      borderRadius: 'var(--r-xl)',
      border: '1px solid rgba(255,255,255,0.06)',
      boxShadow: `0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1), 0 0 60px ${glowColor}10`,
      transition: 'all 0.4s cubic-bezier(0.2, 0.8, 0.2, 1)',
    }}
      onMouseEnter={e => { (e.currentTarget).style.boxShadow = `0 12px 48px rgba(0,0,0,0.60), inset 0 1px 0 rgba(255,255,255,0.15), 0 0 80px ${glowColor}25`; (e.currentTarget).style.transform = 'translateY(-4px)'; (e.currentTarget).style.borderColor = 'rgba(255,255,255,0.1)'; }}
      onMouseLeave={e => { (e.currentTarget).style.boxShadow = `0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1), 0 0 60px ${glowColor}10`; (e.currentTarget).style.transform = 'translateY(0)'; (e.currentTarget).style.borderColor = 'rgba(255,255,255,0.06)'; }}
    >
      {/* Ambient glow orb */}
      <div style={{
        position: 'absolute', top: '-40px', right: '-40px',
        width: '200px', height: '200px',
        background: `radial-gradient(circle, ${glowColor}20, transparent 70%)`,
        pointerEvents: 'none',
        transition: 'all 0.5s ease',
      }} className="group-hover:opacity-100 opacity-60" />

      {/* Top accent line */}
      <div style={{
        position: 'absolute', top: 0, left: '5%', right: '5%', height: '1.5px',
        background: `linear-gradient(90deg, transparent, ${color}80, transparent)`,
      }} />

      {/* Header */}
      <div style={{ padding: '24px 28px 0', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
          <div style={{
            padding: '6px', borderRadius: '8px',
            background: `linear-gradient(135deg, ${color}25, ${color}10)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 0 15px ${color}20, inset 0 1px 1px rgba(255,255,255,0.2)`,
            border: `0.5px solid ${color}30`,
          }}>
            <Icon style={{ width: '16px', height: '16px', color: color }} strokeWidth={2.5} />
          </div>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'rgba(255,255,255,0.6)', letterSpacing: '0.01em', textTransform: 'uppercase' }}>{title}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="font-display" style={{
            fontSize: '44px', fontWeight: 700, letterSpacing: '-0.04em',
            color: '#fff', lineHeight: 1,
            textShadow: `0 2px 20px ${glowColor}40`,
          }}>{value}</span>
          <span style={{ fontSize: '18px', fontWeight: 600, color: 'rgba(255,255,255,0.4)' }}>{unit}</span>
        </div>
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0, marginTop: '-5px', position: 'relative' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 30, right: 0, left: 0, bottom: 0 }}>
            <defs>
              {/* Gradient stroke */}
              <linearGradient id={strokeGradId} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={color} />
                <stop offset="100%" stopColor={colorEnd} />
              </linearGradient>
              {/* Fill gradient */}
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                <stop offset="40%" stopColor={color} stopOpacity={0.15} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
              {/* Advanced Glow filter */}
              <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur1" />
                <feGaussianBlur in="SourceGraphic" stdDeviation="8" result="blur2" />
                <feMerge result="blur">
                  <feMergeNode in="blur1" />
                  <feMergeNode in="blur2" />
                </feMerge>
                <feFlood floodColor={color} floodOpacity="0.6" result="color" />
                <feComposite in="color" in2="blur" operator="in" result="glow" />
                <feMerge>
                  <feMergeNode in="glow" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <CartesianGrid strokeDasharray="4 4" vertical={false} stroke="rgba(255,255,255,0.03)" />
            <YAxis hide domain={[min - padding, max + padding]} />
            <Tooltip
              cursor={{ stroke: 'rgba(255,255,255,0.15)', strokeWidth: 1.5, strokeDasharray: '4 4' }}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div style={{
                      background: 'rgba(20,20,25,0.85)', backdropFilter: 'blur(20px)',
                      border: '1px solid rgba(255,255,255,0.15)', padding: '8px 16px', borderRadius: '10px',
                      boxShadow: `0 8px 32px rgba(0,0,0,0.4), 0 0 20px ${color}20`,
                      fontSize: '15px', fontWeight: 700, color: '#fff',
                      display: 'flex', alignItems: 'baseline', gap: '4px'
                    }}>
                      <span className="num">{parseFloat(payload[0].value as string).toFixed(2)}</span>
                      <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>{unit}</span>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={`url(#${strokeGradId})`}
              strokeWidth={3}
              fill={`url(#${gradId})`}
              filter={`url(#${filterId})`}
              activeDot={{ r: 6, fill: '#fff', stroke: color, strokeWidth: 2, filter: `drop-shadow(0 0 8px ${color})` }}
              animationDuration={1500}
            />
          </AreaChart>
        </ResponsiveContainer>
        {/* Bottom border fade */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: '40px',
          background: 'linear-gradient(0deg, rgba(5,5,8,0.8) 0%, transparent 100%)',
          pointerEvents: 'none'
        }} />
      </div>
    </div>
  );
}
