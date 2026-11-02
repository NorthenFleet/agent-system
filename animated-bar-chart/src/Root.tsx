import {AbsoluteFill, Composition, Easing, Interactive, interpolate, useCurrentFrame} from 'remotion';

const Bar = ({label, value, color, left, delay}: {label: string; value: number; color: string; left: number; delay: number}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [delay, delay + 55], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)});
  return <div style={{position: 'absolute', left, bottom: 0, width: 120, height: 390}}>
    <div style={{position: 'absolute', bottom: value * 3.9 * progress + 18, width: '100%', textAlign: 'center', fontSize: 38, fontWeight: 650, color, opacity: interpolate(frame, [delay, delay + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), fontVariantNumeric: 'tabular-nums'}}>{Math.round(value * progress)}</div>
    <div style={{position: 'absolute', bottom: 0, width: 120, height: value * 3.9 * progress, background: `linear-gradient(180deg, ${color}, ${color}99)`, borderRadius: '12px 12px 0 0', boxShadow: `0 0 45px ${color}18`}} />
    <div style={{position: 'absolute', top: 411, width: '100%', textAlign: 'center', fontSize: 24, color: '#aeb8c9'}}>{label}</div>
  </div>;
};

export const FiveBars = () => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{background: '#0b1120', fontFamily: 'Arial, Helvetica, sans-serif', color: '#f3f6fc'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 80% 0%, #19334980, transparent 65%)'}} />
    <Interactive.Div name="Eyebrow" style={{position: 'absolute', left: 90, top: 54, fontSize: 18, letterSpacing: 4, color: '#6fe3cd', opacity: interpolate(frame, [0, 16], [0, 1], {extrapolateRight: 'clamp'})}}>FIVE CATEGORIES · ONE VIEW</Interactive.Div>
    <Interactive.Div name="Title" style={{position: 'absolute', left: 86, top: 90, fontSize: 76, fontWeight: 700, letterSpacing: -3, opacity: interpolate(frame, [0, 22], [0, 1], {extrapolateRight: 'clamp'}), translate: interpolate(frame, [0, 22], ['0px 16px', '0px 0px'], {extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)})}}>A little perspective.</Interactive.Div>
    <Interactive.Div name="Subtitle" style={{position: 'absolute', left: 90, top: 184, fontSize: 24, color: '#aeb8c9', opacity: interpolate(frame, [10, 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>Sample scores across five categories</Interactive.Div>
    <div style={{position: 'absolute', left: 150, top: 274, width: 1010, height: 390, opacity: interpolate(frame, [16, 32], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
      {[0, 25, 50, 75, 100].map(tick => <div key={tick} style={{position: 'absolute', bottom: tick * 3.9, width: '100%', borderTop: `1px solid ${tick === 0 ? '#657088' : '#ffffff12'}`}}><span style={{position: 'absolute', right: 'calc(100% + 22px)', top: -11, color: '#748198', fontSize: 18}}>{tick}</span></div>)}
      <Bar label="Alpha" value={42} color="#67d9ef" left={38} delay={26} />
      <Bar label="Beta" value={68} color="#7ca4ff" left={236} delay={36} />
      <Bar label="Gamma" value={55} color="#b79aff" left={434} delay={46} />
      <Bar label="Delta" value={84} color="#6fe3cd" left={632} delay={56} />
      <Bar label="Epsilon" value={96} color="#e3ee9d" left={830} delay={66} />
    </div>
    <Interactive.Div name="Footnote" style={{position: 'absolute', left: 90, bottom: 34, fontSize: 17, color: '#748198'}}>ILLUSTRATIVE DATA</Interactive.Div>
    <Interactive.Div name="Scale" style={{position: 'absolute', right: 90, bottom: 34, fontSize: 17, color: '#748198'}}>SCORE / 100</Interactive.Div>
  </AbsoluteFill>;
};

export const RemotionRoot = () => <Composition id="FiveBars" component={FiveBars} durationInFrames={210} fps={30} width={1280} height={800} defaultProps={{}} />;
