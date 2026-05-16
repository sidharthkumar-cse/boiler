import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { STAT_CARDS, ANALYTICS_DATA } from "../../lib/mock-data";
import { AnimatedValue } from "../ui/animated-value";
import { Sparkline } from "../ui/sparkline";

interface StatCardData {
  id: string;
  label: string;
  value: string;
  unit: string;
  trend?: number;
  bar: number;
  sub: string;
  icon: React.ComponentType<any>;
  accent: string;
  accentAlpha: string;
  description: string;
  sparkData?: number[];
}

export function StatCard({ card, index }: { card: StatCardData; index: number }) {
  const Icon = card.icon;
  const trend = card.trend ?? 0;
  const up = trend > 0;
  
  // Generate sparkline data from the card value
  const sparkData = card.sparkData || (card.id === 'pressure' 
    ? ANALYTICS_DATA.map(d => d.pressure)
    : card.id === 'temperature'
    ? ANALYTICS_DATA.map(d => d.temperature)
    : card.id === 'water'
    ? ANALYTICS_DATA.map(d => d.waterLevel)
    : ANALYTICS_DATA.map(d => d.vP / 100 * 95 + 90)); // efficiency proxy

  return (
    <div
      className={`card animate-fade-up delay-${index + 1}`}
      style={{ padding: '20px 22px 18px', position: 'relative', overflow: 'hidden' }}
    >
      {/* Accent glow top edge */}
      <div style={{
        position: 'absolute', top: 0, left: '10%', right: '10%', height: '1px',
        background: `linear-gradient(90deg, transparent, ${card.accent}66, transparent)`,
      }} />

      {/* Subtle background accent glow */}
      <div style={{
        position: 'absolute', top: '-20px', right: '-20px', width: '100px', height: '100px',
        background: `radial-gradient(circle, ${card.accent}08, transparent 70%)`,
        pointerEvents: 'none',
      }} />

      {/* Top row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '9px' }}>
          <div style={{
            width: '34px', height: '34px', borderRadius: '10px',
            background: `linear-gradient(145deg, ${card.accentAlpha}, ${card.accent}08)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: `0.5px solid ${card.accent}20`,
            boxShadow: `0 2px 8px ${card.accent}12`,
          }}>
            <Icon style={{ width: '15px', height: '15px', color: card.accent }} strokeWidth={2} />
          </div>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--t3)', letterSpacing: '0.02em', textTransform: 'uppercase' }}>
              {card.label}
            </div>
          </div>
        </div>

        {/* Trend badge */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '2px',
          padding: '3px 8px', borderRadius: '99px',
          background: up ? 'rgba(48,209,88,0.09)' : 'rgba(255,59,48,0.09)',
          border: `0.5px solid ${up ? 'rgba(48,209,88,0.22)' : 'rgba(255,59,48,0.22)'}`,
          fontSize: '11px', fontWeight: 600,
          color: up ? '#1a8f3c' : '#c0392b',
        }}>
          {up
            ? <ArrowUpRight style={{ width: '10px', height: '10px' }} strokeWidth={2.5} />
            : <ArrowDownRight style={{ width: '10px', height: '10px' }} strokeWidth={2.5} />}
          {Math.abs(trend)}%
        </div>
      </div>

      {/* Value + Sparkline row */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div className="stat-value-glow" style={{ display: 'flex', alignItems: 'baseline', gap: '5px' }}>
          <span className="font-display" style={{
            fontSize: '38px', fontWeight: 600,
            letterSpacing: '-0.035em', color: 'var(--t1)', lineHeight: 1,
          }}>
            <AnimatedValue value={card.value} />
          </span>
          <span style={{ fontSize: '14px', color: 'var(--t3)', fontWeight: 500, letterSpacing: '-0.01em' }}>
            {card.unit}
          </span>
          <div className="stat-value-glow" style={{ position: 'absolute', bottom: '45px', left: '22px', right: '60%', height: '12px', background: card.accent, filter: 'blur(14px)', opacity: 0.12, borderRadius: '50%', pointerEvents: 'none' }} />
        </div>
        <Sparkline data={sparkData} color={card.accent} />
      </div>

      {/* Progress bar */}
      <div className="progress-track" style={{ marginBottom: '10px' }}>
        <div
          className="progress-fill"
          style={{
            width: `${card.bar}%`,
            background: `linear-gradient(90deg, ${card.accent}cc, ${card.accent})`,
          }}
        />
      </div>

      {/* Sub label */}
      <p style={{ fontSize: '11px', color: 'var(--t3)', fontWeight: 500, letterSpacing: '0.005em' }}>
        {card.description}
      </p>
    </div>
  );
}
