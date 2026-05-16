'use client';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface BoilerSchematicProps {
  isHeating: boolean;
  mode: string;
  onToggleHeater: () => void;
  onSetAuto: () => void;
  isLoading?: boolean;
}

export default function BoilerSchematic({ isHeating, mode, onToggleHeater, onSetAuto, isLoading }: BoilerSchematicProps) {
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px', gap: '0px' }}>

      {/* Heating toggle — Apple-grade pill */}
      <svg viewBox="0 -40 800 640" style={{ width: '100%', flex: '1 1 auto', minHeight: 0 }} preserveAspectRatio="xMidYMid meet">
        <defs>
          {/* ── Filters ── */}
          <filter id="ag-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="ag-heat-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="ag-steam" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
          <filter id="ag-dot" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="1.5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>

          {/* ── Gradients ── */}

          {/* Tank – light steel with subtle cool sheen */}
          <linearGradient id="ag-tank" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#b8c4d0" />
            <stop offset="12%" stopColor="#cdd8e3" />
            <stop offset="50%" stopColor="#dae4ec" />
            <stop offset="88%" stopColor="#cdd8e3" />
            <stop offset="100%" stopColor="#b8c4d0" />
          </linearGradient>

          {/* Glass sheen */}
          <linearGradient id="ag-glass" x1="0" y1="0" x2="1" y2="0.6">
            <stop offset="0%" stopColor="rgba(255,255,255,0.55)" />
            <stop offset="30%" stopColor="rgba(255,255,255,0.10)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0.20)" />
          </linearGradient>

          {/* Water — vivid blue */}
          <linearGradient id="ag-water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#42a5f5" stopOpacity="0.95" />
            <stop offset="35%" stopColor="#1976d2" />
            <stop offset="100%" stopColor="#0d47a1" />
          </linearGradient>

          {/* Pipe — horizontal (3D cylinder, light steel) */}
          <linearGradient id="ag-pipe-h" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8a9aaa" />
            <stop offset="22%" stopColor="#b0bec5" />
            <stop offset="46%" stopColor="#cfd8dc" />
            <stop offset="54%" stopColor="#cfd8dc" />
            <stop offset="78%" stopColor="#b0bec5" />
            <stop offset="100%" stopColor="#78909c" />
          </linearGradient>

          {/* Pipe — vertical */}
          <linearGradient id="ag-pipe-v" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#78909c" />
            <stop offset="22%" stopColor="#b0bec5" />
            <stop offset="46%" stopColor="#cfd8dc" />
            <stop offset="54%" stopColor="#cfd8dc" />
            <stop offset="78%" stopColor="#b0bec5" />
            <stop offset="100%" stopColor="#8a9aaa" />
          </linearGradient>

          {/* Valve body */}
          <linearGradient id="ag-valve" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8fa8be" />
            <stop offset="100%" stopColor="#607d8b" />
          </linearGradient>

          {/* Clip for tank interior */}
          <clipPath id="ag-tank-clip">
            <rect x="260" y="80" width="280" height="440" rx="56" />
          </clipPath>
        </defs>

        {/* ══════════════ TANK ══════════════ */}

        {/* Support legs */}
        <rect x="307" y="520" width="16" height="38" rx="3" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" />
        <rect x="477" y="520" width="16" height="38" rx="3" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" />
        <rect x="302" y="553" width="26" height="5" rx="2.5" fill="#90a4ae" />
        <rect x="472" y="553" width="26" height="5" rx="2.5" fill="#90a4ae" />
        {/* Floor shadow */}
        <ellipse cx="400" cy="562" rx="110" ry="7" fill="rgba(0,0,0,0.12)" />

        {/* Tank body */}
        <rect x="260" y="80" width="280" height="440" rx="56" fill="url(#ag-tank)" stroke="#90a4ae" strokeWidth="1" />

        {/* ─── Interior (clipped) ─── */}
        <g clipPath="url(#ag-tank-clip)">

          {/* Water fill base */}
          <rect x="260" y="280" width="280" height="260" fill="#0d47a1" />
          {/* Water animated surface */}
          <motion.rect
            x="260" y="280" width="280" height="260"
            fill="url(#ag-water)"
            animate={{ y: [280, 285, 280] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* Bubbles when heating */}
          <AnimatePresence>
            {isHeating && (
              <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 1 }}>
                {[
                  // Plume 1 (Left)
                  { x: 310, y: 440, r: 3, dur: 1.8, delay: 0, wx: 12 },
                  { x: 315, y: 450, r: 4, dur: 2.1, delay: 0.4, wx: -8 },
                  { x: 305, y: 435, r: 2, dur: 1.5, delay: 0.8, wx: 10 },
                  { x: 312, y: 445, r: 5, dur: 1.9, delay: 1.2, wx: -12 },
                  // Plume 2 (Mid-Left)
                  { x: 370, y: 430, r: 4, dur: 1.7, delay: 0.2, wx: -15 },
                  { x: 380, y: 435, r: 5, dur: 2.0, delay: 0.7, wx: 10 },
                  { x: 375, y: 425, r: 3, dur: 1.4, delay: 1.1, wx: -8 },
                  { x: 365, y: 440, r: 2, dur: 1.6, delay: 1.5, wx: 12 },
                  // Plume 3 (Mid-Right)
                  { x: 440, y: 450, r: 3, dur: 1.9, delay: 0.1, wx: 14 },
                  { x: 450, y: 440, r: 5, dur: 2.2, delay: 0.6, wx: -10 },
                  { x: 445, y: 445, r: 4, dur: 1.8, delay: 0.9, wx: 12 },
                  { x: 435, y: 435, r: 2, dur: 1.5, delay: 1.4, wx: -10 },
                  // Plume 4 (Right)
                  { x: 500, y: 420, r: 5, dur: 2.0, delay: 0.3, wx: -12 },
                  { x: 510, y: 430, r: 4, dur: 1.7, delay: 0.8, wx: 10 },
                  { x: 495, y: 425, r: 3, dur: 1.5, delay: 1.3, wx: -14 },
                  { x: 505, y: 440, r: 2, dur: 1.6, delay: 0.5, wx: 8 },
                  // Extra stray bubbles
                  { x: 410, y: 450, r: 6, dur: 2.5, delay: 0.5, wx: 20 },
                  { x: 340, y: 415, r: 4, dur: 1.8, delay: 1.0, wx: -15 },
                ].map(({ x, y, r, dur, delay, wx }, i) => (
                  <motion.circle key={`bubble-${i}`}
                    r={r}
                    fill="rgba(255,255,255,0.25)"
                    stroke="rgba(255,255,255,0.9)"
                    strokeWidth="1.2"
                    animate={{
                      cx: [x, x + wx, x - wx, x + (wx / 2), x],
                      cy: [y, y - 40, y - 90, 290, 280],
                      opacity: [0, 0.8, 1, 0.8, 0],
                      scale: [0.2, 0.7, 1.2, 1.8, 2.5]
                    }}
                    transition={{ duration: dur, repeat: Infinity, ease: 'linear', delay }}
                  />
                ))}
              </motion.g>
            )}
          </AnimatePresence>

          {/* Steam cloud when heating */}
          <AnimatePresence>
            {isHeating && (
              <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 1.0 }}>
                {/* Background steam shadow for depth and contrast */}
                <motion.g filter="url(#ag-steam)" fill="#90a4ae" opacity="0.85">
                  <motion.ellipse cx="400" cy="195" rx="125" ry="40"
                    animate={{ rx: [125, 155, 110, 125], ry: [40, 60, 35, 40], opacity: [0.5, 0.9, 0.6, 0.5], x: [-20, 25, -15, -20] }}
                    transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="320" cy="160" r="60"
                    animate={{ x: [0, 55, -25, 0], y: [0, -35, 15, 0], scale: [1, 1.35, 0.9, 1] }}
                    transition={{ duration: 2.1, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="480" cy="150" r="65"
                    animate={{ x: [0, -60, 30, 0], y: [0, -40, 10, 0], scale: [1, 1.4, 0.85, 1] }}
                    transition={{ duration: 1.9, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="400" cy="135" r="55"
                    animate={{ x: [-30, 45, -15, -30], y: [0, -50, 10, 0], scale: [1, 1.5, 0.9, 1] }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }} />
                </motion.g>

                {/* Foreground bright steam */}
                <motion.g filter="url(#ag-steam)" fill="#ffffff" opacity="1">
                  <motion.ellipse cx="400" cy="200" rx="120" ry="36"
                    animate={{ opacity: [0.7, 1, 0.8, 0.7], ry: [36, 60, 30, 36], rx: [120, 150, 110, 120], x: [-15, 20, -15] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="330" cy="165" r="55" fill="#e8f4fd"
                    animate={{ x: [0, 60, -30, 0], y: [0, -40, 15, 0], scale: [1, 1.45, 0.9, 1] }}
                    transition={{ duration: 1.7, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="470" cy="150" r="60"
                    animate={{ x: [0, -55, 35, 0], y: [0, -45, 10, 0], scale: [1, 1.35, 0.85, 1] }}
                    transition={{ duration: 1.65, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="390" cy="140" r="55" fill="#f0f7ff"
                    animate={{ x: [-35, 50, -20, -35], y: [0, -55, 10, 0], scale: [0.9, 1.5, 0.8, 0.9] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="430" cy="130" r="50" fill="#ffffff"
                    animate={{ x: [35, -45, 20, 35], y: [10, -40, 5, 10], scale: [1, 1.5, 0.85, 1] }}
                    transition={{ duration: 1.3, repeat: Infinity, ease: 'easeInOut' }} />
                  <motion.circle cx="360" cy="135" r="45" fill="#ffffff"
                    animate={{ x: [-45, 35, -20, -45], y: [15, -35, 5, 15], scale: [1, 1.45, 0.9, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }} />
                </motion.g>
              </motion.g>
            )}
          </AnimatePresence>

          {/* Heating coil — W-shape */}
          <motion.path
            d="M 540 400 L 300 400 C 280 400, 280 418, 300 418 L 500 418 C 520 418, 520 436, 500 436 L 300 436 C 280 436, 280 454, 300 454 L 540 454"
            fill="none" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round"
            filter={isHeating ? 'url(#ag-heat-glow)' : undefined}
            animate={isHeating
              ? { stroke: ['#e65100', '#ff8a65', '#e65100'] }
              : { stroke: '#90a4ae' }}
            transition={{ duration: isHeating ? 2.5 : 0.6, repeat: isHeating ? Infinity : 0 }}
          />
          {/* Coil hot highlight */}
          <AnimatePresence>
            {isHeating && (
              <motion.path
                d="M 540 400 L 300 400 C 280 400, 280 418, 300 418 L 500 418 C 520 418, 520 436, 500 436 L 300 436 C 280 436, 280 454, 300 454 L 540 454"
                fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round"
                initial={{ opacity: 0 }} animate={{ opacity: 0.5 }} exit={{ opacity: 0 }}
                style={{ filter: 'blur(2px)' }}
              />
            )}
          </AnimatePresence>

          {/* Water surface waveline */}
          <motion.path
            d="M 260 278 Q 345 272, 400 282 T 540 278"
            fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5"
            animate={{ d: ['M 260 278 Q 345 272, 400 282 T 540 278', 'M 260 282 Q 345 288, 400 275 T 540 282', 'M 260 278 Q 345 272, 400 282 T 540 278'] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
          />
        </g>

        {/* Tank glass overlay */}
        <rect x="260" y="80" width="280" height="440" rx="56" fill="url(#ag-glass)" stroke="rgba(255,255,255,0.6)" strokeWidth="1.2" />
        {/* Left edge specular */}
        <path d="M 270 150 L 270 450" stroke="rgba(255,255,255,0.4)" strokeWidth="2.5" strokeLinecap="round" />
        {/* Top specular arc */}
        <path d="M 345 84 Q 400 80, 455 84" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" strokeLinecap="round" />


        {/* ══════════════ WATER LEVEL GAUGE ══════════════ */}
        <g>
          <line x1="254" y1="290" x2="254" y2="500" stroke="#90a4ae" strokeWidth="2.5" strokeLinecap="round" />
          <line x1="254" y1="290" x2="254" y2="500" stroke="#1e88e5" strokeWidth="1" strokeLinecap="round" opacity="0.4" />
          {[290, 350, 410, 470].map(y => (
            <line key={y} x1="248" y1={y} x2="257" y2={y} stroke="#90a4ae" strokeWidth="1.2" />
          ))}
          <circle cx="254" cy="285" r="3.5" fill="#1e88e5" filter="url(#ag-dot)" />
        </g>


        {/* ══════════════ PIPES ══════════════ */}

        {/* ─── Water Inlet (Bottom Left) ─── */}
        <g transform="translate(0, 460)">
          <path d="M 60 0 L 260 0" stroke="#9eb2be" strokeWidth="26" />
          <path d="M 60 0 L 260 0" stroke="url(#ag-pipe-h)" strokeWidth="22" />
          {/* Flanges */}
          <rect x="252" y="-13" width="9" height="26" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          <rect x="58" y="-13" width="9" height="26" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          {/* Flow indicator */}
          <path d="M 65 0 L 255 0" stroke="#1e88e5" strokeWidth="3" strokeDasharray="14 20" fill="none" opacity="0.35" filter="url(#ag-dot)">
            <animate attributeName="stroke-dashoffset" values="34;0" dur="1.1s" repeatCount="indefinite" />
          </path>
          {/* Gate valve */}
          <g transform="translate(112, 0)">
            <rect x="-16" y="-13" width="7" height="26" fill="#90a4ae" rx="1" />
            <rect x="9" y="-13" width="7" height="26" fill="#90a4ae" rx="1" />
            <polygon points="-10,-14 10,14 10,-14 -10,14" fill="url(#ag-valve)" stroke="#90a4ae" strokeWidth="1.2" strokeLinejoin="round" />
            <rect x="-13" y="-35" width="26" height="18" fill="#cdd8e3" stroke="#90a4ae" strokeWidth="0.8" rx="3" />
            <circle cx="0" cy="-26" r="2.5" fill="#1a8f3c" opacity="0.9" filter="url(#ag-dot)" />
          </g>
          {/* Flow meter */}
          <g transform="translate(192, 0)">
            <circle cx="0" cy="0" r="19" fill="#dae4ec" stroke="#90a4ae" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="14" fill="#cdd8e3" />
            <motion.g animate={{ rotate: 360 }} transition={{ duration: 2.8, repeat: Infinity, ease: 'linear' }}>
              <path d="M 0 -9 L 0 9 M -9 0 L 9 0" stroke="#90a4ae" strokeWidth="1.5" />
              <circle cx="0" cy="0" r="2.5" fill="#607d8b" />
            </motion.g>
          </g>
          <text x="66" y="-42" fill="#546e7a" fontSize="9" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">WATER IN</text>
        </g>

        {/* ─── Water Level Float Switch (Left) ─── */}
        {/* Horizontal stub pipe connecting tank to float tube */}
        <g transform="translate(260, 300)">
          <path d="M 0 0 L -28 0" stroke="#9eb2be" strokeWidth="14" />
          <path d="M 0 0 L -28 0" stroke="url(#ag-pipe-v)" strokeWidth="10" />
        </g>
        <g transform="translate(260, 440)">
          <path d="M 0 0 L -28 0" stroke="#9eb2be" strokeWidth="14" />
          <path d="M 0 0 L -28 0" stroke="url(#ag-pipe-v)" strokeWidth="10" />
        </g>

        {/* Float switch vertical sight tube */}
        <g transform="translate(232, 285)">
          {/* Tube background */}
          <rect x="-6" y="0" width="12" height="165" rx="6" fill="#dae4ec" stroke="#90a4ae" strokeWidth="1.2" />
          {/* Inner tube channel */}
          <rect x="-3" y="3" width="6" height="159" rx="3" fill="#edf2f7" />

          {/* Water fill inside the tube */}
          <rect x="-3" y="83" width="6" height="79" rx="2" fill="#1976d2" opacity="0.85" />
          {/* Animated water surface in tube */}
          <motion.rect
            x="-3" y="83" width="6" height="4" rx="2"
            fill="#42a5f5" opacity="0.9"
            animate={{ y: [83, 86, 83] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* High level tick + label */}
          <line x1="-10" y1="28" x2="10" y2="28" stroke="#90a4ae" strokeWidth="1.2" />
          <text x="-16" y="32" fill="#546e7a" fontSize="9" fontWeight="700" letterSpacing="1" textAnchor="end" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">HI</text>

          {/* Low level tick + label */}
          <line x1="-10" y1="137" x2="10" y2="137" stroke="#90a4ae" strokeWidth="1.2" />
          <text x="-16" y="141" fill="#546e7a" fontSize="9" fontWeight="700" letterSpacing="1" textAnchor="end" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">LO</text>

          {/* Float ball */}
          <motion.circle
            cx="0" cy="83" r="7"
            fill="url(#ag-valve)" stroke="#607d8b" strokeWidth="1.2"
            animate={{ cy: [83, 86, 83] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
          />
          {/* Float ball sheen */}
          <motion.circle
            cx="-2" cy="80" r="2.5"
            fill="rgba(255,255,255,0.55)"
            animate={{ cy: [80, 83, 80] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
          />
          {/* Glowing status dot */}
          <circle cx="0" cy="83" r="2" fill="#1e88e5" opacity="0.7" filter="url(#ag-dot)">
            <animate attributeName="opacity" values="0.7;0.25;0.7" dur="2.2s" repeatCount="indefinite" />
          </circle>

          {/* Top cap */}
          <rect x="-7" y="-4" width="14" height="7" rx="3" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.8" />
          {/* Bottom cap */}
          <rect x="-7" y="161" width="14" height="7" rx="3" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.8" />
        </g>

        {/* Float switch label */}
        <text x="140" y="356" fill="#546e7a" fontSize="9" fontWeight="700" letterSpacing="1.2" textAnchor="end" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">WATER LEVEL</text>
        <text x="140" y="368" fill="#546e7a" fontSize="9" fontWeight="700" letterSpacing="1.2" textAnchor="end" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">FLOAT SWITCH</text>

        {/* ─── Pressure Sensor (Top Left) ─── */}
        <g transform="translate(340, 80)">
          <path d="M 0 0 L 0 -26" stroke="#9eb2be" strokeWidth="20" />
          <path d="M 0 0 L 0 -26" stroke="url(#ag-pipe-v)" strokeWidth="16" />
          <rect x="-11" y="-30" width="22" height="7" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          <rect x="-17" y="-50" width="34" height="18" fill="#dae4ec" stroke="#90a4ae" strokeWidth="0.8" rx="3" />
          <rect x="-9" y="-47" width="18" height="11" fill="#edf2f7" rx="2" />
          <path d="M -6 -41 L -2 -41 L 0 -44 L 3 -38 L 6 -41" stroke="#1a8f3c" strokeWidth="1" fill="none" opacity="0.9" />
          <text x="-32" y="-58" fill="#546e7a" fontSize="11" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">PRESSURE</text>
        </g>

        {/* ─── Safety / Relief Valve (Top Right) ─── */}
        <g transform="translate(460, 80)">
          <path d="M 0 0 L 0 -20" stroke="#9eb2be" strokeWidth="20" />
          <path d="M 0 0 L 0 -20" stroke="url(#ag-pipe-v)" strokeWidth="16" />
          <rect x="-11" y="-24" width="22" height="7" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          <rect x="-15" y="-46" width="30" height="22" fill="#dae4ec" stroke="#90a4ae" strokeWidth="0.8" rx="3" />
          <path d="M -7 -50 L 7 -50 M -9 -56 L 9 -56 M -7 -62 L 7 -62" stroke="#90a4ae" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M 0 -46 L 0 -66" stroke="#78909c" strokeWidth="2.5" />
          <rect x="-5" y="-70" width="10" height="4" fill="#78909c" rx="1" />
          <text x="-22" y="-78" fill="#546e7a" fontSize="11" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">RELIEF</text>
        </g>

        {/* ─── Steam Outlet (Right Upper) ─── */}
        <g transform="translate(540, 162)">
          <path d="M 0 0 L 175 0" stroke="#9eb2be" strokeWidth="26" />
          <path d="M 0 0 L 175 0" stroke="url(#ag-pipe-h)" strokeWidth="22" />
          <rect x="-2" y="-13" width="9" height="26" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          <rect x="168" y="-13" width="9" height="26" fill="#b0bec5" stroke="#90a4ae" strokeWidth="0.5" rx="1" />
          {/* Steam flow — only when heating */}
          {isHeating && (
            <g>
              <path d="M 4 0 L 171 0" stroke="rgba(0,113,227,0.5)" strokeWidth="10" strokeDasharray="20 15" fill="none">
                <animate attributeName="stroke-dashoffset" values="35;0" dur="0.25s" repeatCount="indefinite" />
              </path>
              <path d="M 4 0 L 171 0" stroke="#ffffff" strokeWidth="4" strokeDasharray="30 20" fill="none">
                <animate attributeName="stroke-dashoffset" values="50;0" dur="0.2s" repeatCount="indefinite" />
              </path>
            </g>
          )}
          {/* Valve */}
          <g transform="translate(68, 0)">
            <rect x="-16" y="-13" width="7" height="26" fill="#90a4ae" rx="1" />
            <rect x="9" y="-13" width="7" height="26" fill="#90a4ae" rx="1" />
            <polygon points="-10,-14 10,14 10,-14 -10,14" fill="url(#ag-valve)" stroke="#90a4ae" strokeWidth="1.2" strokeLinejoin="round" />
            <rect x="-15" y="-38" width="30" height="21" fill="#dae4ec" stroke="#90a4ae" strokeWidth="0.8" rx="3" />
            <circle cx="0" cy="-27" r="4.5" fill="none" stroke="#78909c" strokeWidth="1.2" />
            <circle cx="0" cy="-27" r="1.8" fill="#78909c" />
          </g>
          <text x="104" y="-22" fill="#546e7a" fontSize="11" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">STEAM OUT</text>
        </g>

        {/* ─── Temp Sensor (Right Mid) ─── */}
        <g transform="translate(540, 350)">
          <path d="M 0 0 L 26 0" stroke="#9eb2be" strokeWidth="18" />
          <path d="M 0 0 L 26 0" stroke="url(#ag-pipe-h)" strokeWidth="14" />
          <rect x="24" y="-9" width="11" height="18" fill="#dae4ec" stroke="#90a4ae" strokeWidth="0.8" rx="2" />
          <circle cx="50" cy="0" r="13" fill="#edf2f7" stroke="#90a4ae" strokeWidth="1.2" />
          <text x="44" y="4" fill="#546e7a" fontSize="11" fontWeight="700" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">°C</text>
          <text x="70" y="5" fill="#546e7a" fontSize="11" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">TEMP</text>
        </g>

        {/* ─── Heater Terminals (Right Bottom) ─── */}
        <g transform="translate(540, 430)">
          <rect x="0" y="-26" width="18" height="48" fill="#dae4ec" stroke="#90a4ae" strokeWidth="1.2" rx="3" />
          <path d="M 18 -14 L 38 -14" stroke={isHeating ? '#b96a00' : '#90a4ae'} strokeWidth="4" strokeLinecap="round" />
          <path d="M 18 8 L 38 8" stroke={isHeating ? '#b96a00' : '#90a4ae'} strokeWidth="4" strokeLinecap="round" />
          <circle cx="40" cy="-14" r="3" fill={isHeating ? '#b96a00' : '#90a4ae'} />
          <circle cx="40" cy="8" r="3" fill={isHeating ? '#b96a00' : '#90a4ae'} />
          <text x="50" y="2" fill="#546e7a" fontSize="11" fontWeight="700" letterSpacing="1.4" fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif">PWR</text>
        </g>

        {/* ══════════════ CALLOUT TAG ══════════════ */}
        <g>
          <path d="M 540 258 L 608 258" stroke="rgba(0,0,0,0.12)" strokeWidth="0.8" strokeDasharray="3 4" />
          <g transform="translate(612, 243)">
            <rect width="96" height="28" rx="14" fill="rgba(218,228,236,0.95)" stroke="rgba(0,0,0,0.10)" strokeWidth="0.8" />
            <text x="48" y="18" textAnchor="middle"
              fill="#546e7a"
              fontFamily="-apple-system, BlinkMacSystemFont, 'Inter', sans-serif"
              fontSize="12" fontWeight="700" letterSpacing="1.4">4.0 LITER</text>
          </g>
        </g>

      </svg>

      {/* Heating toggle — Apple-grade pill, below SVG */}
      <button
        onClick={() => {
          if (mode === 'AUTO') onToggleHeater();
          else onSetAuto();
        }}
        disabled={isLoading}
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 26px',
          marginTop: '4px',
          marginBottom: '8px',
          borderRadius: '99px',
          border: `0.5px solid ${isHeating ? 'rgba(185,106,0,0.30)' : 'rgba(0,0,0,0.10)'}`,
          background: isHeating
            ? 'rgba(255,159,10,0.10)'
            : 'rgba(255,255,255,0.82)',
          backdropFilter: 'blur(20px) saturate(180%)',
          WebkitBackdropFilter: 'blur(20px) saturate(180%)',
          boxShadow: isHeating
            ? '0 4px 16px rgba(185,106,0,0.20), 0 1px 4px rgba(0,0,0,0.06)'
            : '0 2px 10px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.05)',
          color: isHeating ? '#b96a00' : 'rgba(29,29,31,0.55)',
          fontSize: '12px',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase' as const,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
          cursor: isLoading ? 'not-allowed' : 'pointer',
          transition: 'all 0.28s cubic-bezier(0.25, 0.1, 0.25, 1)',
          opacity: isLoading ? 0.7 : 1,
        }}
      >
        <div style={{
          position: 'relative',
          width: '8px',
          height: '8px',
        }}>
          {isHeating && (
            <div style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%',
              background: '#b96a00',
              animation: 'pulse-ring 1.6s ease-out infinite',
            }} />
          )}
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: isHeating ? '#b96a00' : 'rgba(0,0,0,0.22)',
            boxShadow: isHeating ? '0 0 8px rgba(185,106,0,0.60)' : 'none',
            transition: 'all 0.3s',
          }} />
        </div>
        {isLoading ? 'Processing...' : (mode === 'AUTO' ? (isHeating ? 'Auto Active' : 'Auto Standby') : (isHeating ? 'Manual On' : 'Manual Off'))}
      </button>
    </div>
  );
}
