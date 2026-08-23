/** 拳头餐盘（签名元素）：扇形面积 ∝ 拳头数，段色 = 食物类别语义色。
 *
 * 早 1:1:1 / 午 2:1:1 / 晚 2:1——份量结构直接可视，形状编码真实信息。
 * 打卡后叠加旋转朱印「吃了」印章（reduced-motion 自动关闭动画）。
 */

import type { RecipeSlot } from '../../types';

interface FistPlateProps {
  slots: RecipeSlot[];
  stamped?: boolean;
  size?: number;
}

/** 扇形弧段路径：从 startAngle 起扫 sweep 度（0° = 12 点方向）。 */
function arc(cx: number, cy: number, r: number, startAngle: number, sweep: number): string {
  const rad = (a: number) => ((a - 90) * Math.PI) / 180;
  const x1 = cx + r * Math.cos(rad(startAngle));
  const y1 = cy + r * Math.sin(rad(startAngle));
  const x2 = cx + r * Math.cos(rad(startAngle + sweep));
  const y2 = cy + r * Math.sin(rad(startAngle + sweep));
  const large = sweep > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
}

export default function FistPlate({ slots, stamped = false, size = 96 }: FistPlateProps) {
  const total = slots.reduce((s, x) => s + x.fists, 0) || 1;
  const c = size / 2;
  const r = c - 5;
  let angle = 0;
  const segs = slots.map((s, i) => {
    const sweep = (s.fists / total) * 360;
    const seg = { key: `${s.slot}-${i}`, kind: s.kind, label: `${s.slot}${s.fists}拳`, d: arc(c, c, r, angle + 0.8, sweep - 1.6) };
    angle += sweep;
    return seg;
  });
  return (
    <div className="fist-plate" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`拳头餐盘，共 ${total} 拳`}>
        {segs.map((sg) => (
          <path key={sg.key} className={`fist-seg kind-${sg.kind}`} d={sg.d}>
            <title>{sg.label}</title>
          </path>
        ))}
        <circle className="fist-plate-core" cx={c} cy={c} r={r * 0.45} />
      </svg>
      <div className="fist-center">
        <span className="fist-center-num">{total}</span>
        <span className="fist-center-unit">拳</span>
      </div>
      {stamped && (
        <div className="fist-stamp">
          <span className="fist-stamp-inner">吃了</span>
        </div>
      )}
    </div>
  );
}
