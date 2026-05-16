import React, { useRef, useState, useEffect } from 'react';

export function HeatGraph3D({ 
  title, subtitle, unit, glowColor, accentGradient,
  data 
}: { 
  title: string; subtitle: string; unit: string; 
  glowColor: string; accentGradient: string;
  data: number[][];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ val: number; gx: number; gy: number; px: number; py: number } | null>(null);
  const GRID = 32; 
  
  // Matrix cache for interaction
  const vertexPositions = useRef<{ gx: number; gy: number; x: number; y: number; val: number }[]>([]);

  // Exact Spectral Colormap for scientific visualization
  const getColor = (t: number, min: number, max: number): [number, number, number] => {
    const ratio = Math.max(0, Math.min(1, (t - min) / (max - min)));
    const stops: [number, number, number, number][] = [
      [0.0,   10,  15, 100],   // Dark Abyss
      [0.15,  15,  50, 200],   // Deep Blue
      [0.30,   0, 150, 255],   // Cyan
      [0.45,   0, 200, 100],   // Emerald
      [0.60, 150, 255,   0],   // Yellow-Green
      [0.75, 255, 200,   0],   // Bright Yellow
      [0.90, 255,  50,   0],   // Burnt Orange
      [1.0,  200,   0,   0],   // Crimson Heat
    ];
    for (let i = 0; i < stops.length - 1; i++) {
      if (ratio >= stops[i][0] && ratio <= stops[i + 1][0]) {
        const t2 = (ratio - stops[i][0]) / (stops[i + 1][0] - stops[i][0]);
        return [
          Math.round(stops[i][1] + (stops[i + 1][1] - stops[i][1]) * t2),
          Math.round(stops[i][2] + (stops[i + 1][2] - stops[i][2]) * t2),
          Math.round(stops[i][3] + (stops[i + 1][3] - stops[i][3]) * t2),
        ];
      }
    }
    return [200, 0, 0];
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const canvasParent = canvas.parentElement;
    if (!canvasParent) return;
    
    const W = canvasParent.clientWidth;
    const H = 450;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    const allVals = data.flat();
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const range = max - min || 1;

    // Advanced Isometric Projection scaling for 32x32 mesh
    const cellW = 10;       
    const cellD = 6;       
    const maxBarH = 200;    
    const originX = W / 2 - 20;  
    const originY = H - 60; 
    
    const toIso = (gx: number, gy: number, h: number): [number, number] => {
      const sx = originX + (gx - gy) * (cellW * 0.85);
      const sy = originY - (gx + gy) * (cellD * 0.6) - h;
      return [sx, sy];
    };

    // 1. Draw mathematical grid bounds (Floor & Walls)
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);

    for (let i = 0; i <= GRID; i += 4) {
      // Floor grid lines
      const [f1x, f1y] = toIso(i, 0, 0); const [f2x, f2y] = toIso(i, GRID, 0);
      ctx.beginPath(); ctx.moveTo(f1x, f1y); ctx.lineTo(f2x, f2y); ctx.stroke();
      const [f3x, f3y] = toIso(0, i, 0); const [f4x, f4y] = toIso(GRID, i, 0);
      ctx.beginPath(); ctx.moveTo(f3x, f3y); ctx.lineTo(f4x, f4y); ctx.stroke();

      // Back walls vertical lines
      const [bv1x, bv1y] = toIso(i, GRID, 0); const [bv2x, bv2y] = toIso(i, GRID, maxBarH);
      ctx.beginPath(); ctx.moveTo(bv1x, bv1y); ctx.lineTo(bv2x, bv2y); ctx.stroke();
      const [bv3x, bv3y] = toIso(GRID, i, 0); const [bv4x, bv4y] = toIso(GRID, i, maxBarH);
      ctx.beginPath(); ctx.moveTo(bv3x, bv3y); ctx.lineTo(bv4x, bv4y); ctx.stroke();
    }

    // Horizontal back wall lines (Z-index guides)
    for (let hTick = 0; hTick <= 5; hTick++) {
      const hPx = (hTick / 5) * maxBarH;
      const [w1x, w1y] = toIso(0, GRID, hPx); const [w2x, w2y] = toIso(GRID, GRID, hPx);
      ctx.beginPath(); ctx.moveTo(w1x, w1y); ctx.lineTo(w2x, w2y); ctx.stroke();
      const [w3x, w3y] = toIso(GRID, 0, hPx);
      ctx.beginPath(); ctx.moveTo(w2x, w2y); ctx.lineTo(w3x, w3y); ctx.stroke();
    }
    ctx.setLineDash([]);

    // 2. Analytical Z-Axis labels
    const axisSteps = 5;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const [axX, axY] = toIso(0, GRID, 0);
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.beginPath(); ctx.moveTo(axX - 10, axY); ctx.lineTo(axX - 10, axY - maxBarH); ctx.stroke();
    
    for (let i = 0; i <= axisSteps; i++) {
      const val = min + (i / axisSteps) * range;
      const h = (i / axisSteps) * maxBarH;
      const [, sy] = toIso(0, GRID, h);
      ctx.beginPath(); ctx.moveTo(axX - 10, sy); ctx.lineTo(axX - 5, sy); ctx.stroke();
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '600 10px SF Mono, Consolas, monospace';
      ctx.fillText(val.toFixed(val < 10 ? 2 : 0), axX - 15, sy);
    }

    const positions: typeof vertexPositions.current = [];

    // Precalculate all vertex locations for the mesh
    const vMesh: { sx: number, sy: number, val: number, h: number }[][] = [];
    for (let gy = 0; gy < GRID; gy++) {
      vMesh[gy] = [];
      for (let gx = 0; gx < GRID; gx++) {
        const val = data[gy][gx];
        const h = Math.max(0, ((val - min) / range) * maxBarH);
        const [sx, sy] = toIso(gx, gy, h);
        vMesh[gy][gx] = { sx, sy, val, h };
        positions.push({ gx, gy, val, x: sx, y: sy });
      }
    }

    // 3. Render Continuous Surface Mesh (Painter's algorithm: Back-to-Front)
    // Draw edges first (skirts) for solid analytical volume
    ctx.fillStyle = 'rgba(10,30,80,0.4)';
    ctx.strokeStyle = 'rgba(0,100,255,0.2)';
    ctx.lineWidth = 1;
    // Left skirting
    for (let gy = GRID - 2; gy >= 0; gy--) {
      const gx = GRID - 1;
      const vT1 = vMesh[gy][gx], vT2 = vMesh[gy+1][gx];
      const [b1x, b1y] = toIso(gx, gy, 0); const [b2x, b2y] = toIso(gx, gy+1, 0);
      ctx.beginPath(); ctx.moveTo(vT1.sx, vT1.sy); ctx.lineTo(vT2.sx, vT2.sy); ctx.lineTo(b2x, b2y); ctx.lineTo(b1x, b1y); ctx.closePath();
      ctx.fill(); ctx.stroke();
    }
    // Right skirting
    for (let gx = GRID - 2; gx >= 0; gx--) {
      const gy = GRID - 1;
      const vT1 = vMesh[gy][gx], vT2 = vMesh[gy][gx+1];
      const [b1x, b1y] = toIso(gx, gy, 0); const [b2x, b2y] = toIso(gx+1, gy, 0);
      ctx.beginPath(); ctx.moveTo(vT1.sx, vT1.sy); ctx.lineTo(vT2.sx, vT2.sy); ctx.lineTo(b2x, b2y); ctx.lineTo(b1x, b1y); ctx.closePath();
      ctx.fill(); ctx.stroke();
    }

    // Draw main Surface Mesh Quadrilaterals
    for (let gy = GRID - 2; gy >= 0; gy--) {
      for (let gx = GRID - 2; gx >= 0; gx--) {
        const v1 = vMesh[gy][gx], v2 = vMesh[gy][gx+1];
        const v3 = vMesh[gy+1][gx+1], v4 = vMesh[gy+1][gx];
        
        const avgVal = (v1.val + v2.val + v3.val + v4.val) / 4;
        const [r, g, b] = getColor(avgVal, min, max);

        // Surface normal directional lighting calculation
        const slopeX = v2.h - v1.h;
        const slopeY = v4.h - v1.h;
        const tilt = (slopeX - slopeY) * 0.012; // Directional light from screen left
        const light = Math.max(0.4, Math.min(1.8, 1 + tilt));

        ctx.beginPath();
        ctx.moveTo(v1.sx, v1.sy);
        ctx.lineTo(v2.sx, v2.sy);
        ctx.lineTo(v3.sx, v3.sy);
        ctx.lineTo(v4.sx, v4.sy);
        ctx.closePath();

        ctx.fillStyle = `rgb(${Math.round(r * light)},${Math.round(g * light)},${Math.round(b * light)})`;
        ctx.fill();
        
        // Analytical Wireframe Net
        ctx.strokeStyle = `rgba(0,0,0,0.15)`;
        ctx.lineWidth = 0.4;
        ctx.stroke();
        
        ctx.strokeStyle = `rgba(255,255,255,0.06)`;
        ctx.lineWidth = 0.4;
        ctx.stroke();
      }
    }

    vertexPositions.current = positions;
  }, [data]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    
    // Nearest neighbor search for vertex hit detection
    let closest: typeof vertexPositions.current[0] | null = null;
    let minDist = 25; // Vertex snap distance
    
    for (let i = 0; i < vertexPositions.current.length; i++) {
        const pos = vertexPositions.current[i];
        const dist = Math.sqrt((mx - pos.x) ** 2 + (my - pos.y) ** 2);
        if (dist < minDist) {
            minDist = dist;
            closest = pos;
        }
    }
    
    if (closest) {
      setHover({ val: closest.val, gx: closest.gx, gy: closest.gy, px: mx, py: my });
    } else {
      setHover(null);
    }
  };

  const min = Math.min(...data.flat());
  const max = Math.max(...data.flat());

  return (
    <div style={{
      position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(165deg, rgba(12,14,24,0.95) 0%, rgba(8,10,18,0.98) 50%, rgba(4,6,12,1) 100%)',
      borderRadius: '24px',
      border: '1px solid rgba(255,255,255,0.1)',
      boxShadow: `0 24px 48px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.1), 0 0 60px ${glowColor}10`,
      padding: '24px 28px',
    }}>
      <div style={{
        position: 'absolute', top: 0, left: '10%', right: '10%', height: '2px',
        background: accentGradient, filter: 'blur(2px)'
      }} />

      {/* Industrial Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', zIndex: 10, position: 'relative' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <h3 className="font-display" style={{ fontSize: '18px', fontWeight: 600, letterSpacing: '-0.02em', color: '#ffffff', margin: 0 }}>{title}</h3>
            <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em', color: 'rgba(255,255,255,0.8)' }}>
              SURFACE PLOT
            </span>
          </div>
          <p style={{ fontSize: '13px', color: 'rgba(255,255,255,0.45)', margin: 0 }}>{subtitle}</p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '6px 14px', borderRadius: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)'
          }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#ff3b30', boxShadow: '0 0 10px rgba(255,59,48,0.8)', animation: 'pulse 2s infinite' }} />
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#fff', letterSpacing: '0.04em' }}>LIVE MESH</span>
          </div>
        </div>
      </div>

      <div ref={containerRef} style={{ display: 'flex', gap: '24px', position: 'relative' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <canvas
            ref={canvasRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHover(null)}
            style={{ display: 'block', cursor: 'crosshair' }}
          />
          
          {/* Scientific Tooltip */}
          {hover && (
            <div style={{
              position: 'absolute',
              left: Math.min(hover.px + 20, (containerRef.current?.clientWidth || 500) - 180),
              top: Math.max(hover.py - 70, 10),
              background: 'rgba(5,10,20,0.95)',
              backdropFilter: 'blur(16px)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '8px',
              padding: '12px 16px',
              boxShadow: `0 16px 32px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.1)`,
              pointerEvents: 'none',
              zIndex: 30,
              fontFamily: 'SF Mono, Consolas, monospace'
            }}>
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.5)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Vertex Data
              </div>
              <div className="num" style={{ fontSize: '24px', fontWeight: 700, color: '#fff', marginBottom: '4px' }}>
                {hover.val.toFixed(hover.val < 10 ? 3 : 1)}<span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', marginLeft: '6px' }}>{unit}</span>
              </div>
              <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)' }}>
                Coords: X:{hover.gx} Y:{hover.gy}
              </div>
            </div>
          )}
        </div>

        {/* Industrial Scale Indicator */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '50px', paddingTop: '10px', position: 'relative' }}>
          <span style={{ fontSize: '10px', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '12px', letterSpacing: '0.06em' }}>{unit}</span>
          <div style={{
            width: '10px', height: '360px', borderRadius: '4px',
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'linear-gradient(to bottom, rgb(200,0,0), rgb(255,50,0), rgb(255,200,0), rgb(150,255,0), rgb(0,200,100), rgb(0,150,255), rgb(15,50,200), rgb(10,15,100))',
          }} />
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '360px', position: 'absolute', right: '-8px', top: '35px' }}>
            {Array.from({ length: 9 }, (_, i) => {
              const val = max - (i / 8) * (max - min);
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '4px', height: '1px', background: 'rgba(255,255,255,0.4)' }} />
                  <span className="num" style={{ fontSize: '9px', fontWeight: 500, color: 'rgba(255,255,255,0.5)', fontFamily: 'SF Mono, monospace' }}>
                    {val.toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
