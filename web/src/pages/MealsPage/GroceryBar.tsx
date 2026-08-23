/** 吸底买菜条：清单入口，常显「够吃到几号 · 待购几项」。 */

import { Button } from 'antd';
import { RightOutlined, ShoppingCartOutlined } from '@ant-design/icons';
import type { GrocerySummary } from '../../types';
import { fmtMD } from '../../utils/date';

export default function GroceryBar({ grocery, onOpen }: { grocery: GrocerySummary | null; onOpen: () => void }) {
  return (
    <div className="grocery-bar">
      <Button type="text" className="grocery-bar-btn" onClick={onOpen}>
        <ShoppingCartOutlined />
        <span className="grocery-bar-title">买菜清单</span>
        {grocery && (
          <span className="grocery-bar-sub">
            够吃到 {fmtMD(grocery.through_date)} · 待购 {grocery.pending} 项
          </span>
        )}
        <RightOutlined style={{ fontSize: 11, color: 'rgba(38,51,44,.4)' }} />
      </Button>
    </div>
  );
}
