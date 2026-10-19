/** Isometric "material blocks" render (DESIGN.md imagery: concrete cubes, wood grain, coloured protrusions). Pure SVG. */

const C = Math.cos(Math.PI / 6);

type Box = { x: number; y: number; w: number; d: number; h: number; top: string; left: string; right: string; tex?: string; label?: string; sub?: string };

function pts(p: [number, number][]) {
  return p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
}

function Block({ x, y, w, d, h, top, left, right, tex, label, sub }: Box) {
  const R: [number, number] = [x + w * C, y + w / 2];
  const F: [number, number] = [x + w * C - d * C, y + w / 2 + d / 2];
  const L: [number, number] = [x - d * C, y + d / 2];
  const T: [number, number] = [x, y];
  const down = ([a, b]: [number, number]): [number, number] => [a, b + h];
  return (
    <g>
      <polygon points={pts([L, F, down(F), down(L)])} fill={left} />
      <polygon points={pts([F, R, down(R), down(F)])} fill={right} />
      <polygon points={pts([T, R, F, L])} fill={top} />
      {tex && (
        <>
          <polygon points={pts([L, F, down(F), down(L)])} fill={`url(#${tex})`} />
          <polygon points={pts([F, R, down(R), down(F)])} fill={`url(#${tex})`} />
          <polygon points={pts([T, R, F, L])} fill={`url(#${tex})`} opacity={0.6} />
        </>
      )}
      {label && (
        <g transform={`matrix(${C},${-0.5},0,1,${F[0] + 14},${F[1] + h * 0.5})`}>
          <text fontFamily="var(--font-display)" fontSize={Math.min(46, w * 0.3)} fill="#000" letterSpacing="-0.5">
            {label}
          </text>
          {sub && (
            <text y={20} fontFamily="var(--font-mono)" fontSize={w > 120 ? 11 : 9} fill="#444">
              {sub}
            </text>
          )}
        </g>
      )}
    </g>
  );
}

export function HeroArt() {
  return (
    <svg className="hero-art" viewBox="95 100 390 430" role="img" aria-label="Isometric blocks labelled Qloo, taste and lift">
      <defs>
        <pattern id="concrete" width="7" height="7" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="2" r="0.7" fill="#000" opacity="0.10" />
          <circle cx="5" cy="5.5" r="0.5" fill="#000" opacity="0.08" />
          <circle cx="4" cy="1" r="0.4" fill="#fff" opacity="0.35" />
        </pattern>
        <pattern id="wood" width="60" height="9" patternUnits="userSpaceOnUse">
          <path d="M0 4 C 15 1, 30 7, 60 3" stroke="#7a5230" strokeWidth="1" fill="none" opacity="0.35" />
          <path d="M0 8 C 20 6, 40 9, 60 7" stroke="#7a5230" strokeWidth="0.6" fill="none" opacity="0.25" />
        </pattern>
      </defs>
      {/* painter's order: back to front */}
      <Block x={373} y={205} w={110} d={110} h={110} top="#f3f3f3" left="#bdbdbd" right="#dcdcdc" tex="concrete" label="LIFT" sub="+23 vs typical" />
      <Block x={373} y={200} w={40} d={40} h={40} top="#fff100" left="#c9be00" right="#e8dc00" />
      <Block x={260} y={210} w={150} d={150} h={150} top="#f3f3f3" left="#bdbdbd" right="#d9d9d9" tex="concrete" label="QLOO" sub="insights · places" />
      <Block x={260} y={125} w={100} d={100} h={110} top="#e9d3b4" left="#b98b5c" right="#d4ac7e" tex="wood" label="TASTE" sub="fit 87" />
      <Block x={260} y={130} w={30} d={30} h={30} top="#000" left="#2f2f2f" right="#444" />
      <Block x={173} y={410} w={50} d={50} h={50} top="#d1ffca" left="#9fdc95" right="#bff3b6" />
    </svg>
  );
}
