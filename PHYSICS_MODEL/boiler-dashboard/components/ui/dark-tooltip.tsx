export function DarkTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const items = [
      { name: 'Pressure', value: data.pressure, unit: 'MPa', color: '#38bdf8', glow: '#38bdf840' },
      { name: 'Temperature', value: data.temperature, unit: '°C', color: '#f97316', glow: '#f9731640' },
      { name: 'Water Level', value: data.waterLevel, unit: '%', color: '#a78bfa', glow: '#a78bfa40' },
    ];
    return (
      <div style={{
        background: 'rgba(15,15,25,0.92)',
        backdropFilter: 'blur(24px) saturate(180%)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '14px',
        padding: '14px 18px',
        boxShadow: '0 12px 40px rgba(0,0,0,0.40), 0 0 1px rgba(255,255,255,0.1)',
      }}>
        <p className="num" style={{ margin: '0 0 10px', fontSize: '12px', fontWeight: 500, color: 'rgba(255,255,255,0.45)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{label}</p>
        {items.map((entry: any, index: number) => (
          <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: index < items.length - 1 ? '8px' : 0 }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: entry.color, boxShadow: `0 0 8px ${entry.glow}` }} />
            <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', flex: 1, minWidth: '80px' }}>{entry.name}</span>
            <span className="num" style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>
              {entry.value} <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.35)', fontWeight: 400 }}>{entry.unit}</span>
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
}
