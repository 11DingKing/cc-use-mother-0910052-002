# 下单资金与持仓冻结业务服务

这是一个使用 Python、FastAPI 与 SQLite 实现的纯后端业务服务，包含领域模型、数据访问、业务编排、接口和异常路径测试。项目可在单个 Linux 应用容器内离线运行，使用本地 SQLite 或内存替身，不依赖外部运行服务。

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 测试

```bash
python3 -m pytest -q
```

## 构建检查

```bash
python3 -m compileall -q app
```

## API 导入冒烟

```bash
python3 -c "from app.main import app; print(len(app.routes))"
```

## 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 资金与持仓冻结机制

为支持并发下单，模拟适配器对每一笔订单维护显式、可追踪的冻结台账
（`app/trading/ledger.py`），所有状态变更在同一把交易锁内原子提交：

- **确认即冻结**：下单确认时把冻结单价、数量、预估费用快照固定到订单；
  买单冻结现金（市价单按含滑点上限保守冻结），卖单冻结持仓。
- **守恒不变量**（每次变更后强校验，违例即回滚）：
  - 现金：`capital_cash = available_cash + frozen_cash + settled_cash`
  - 持仓：`quantity = available_quantity + frozen_quantity`
- **部分成交**：冻结按笔转已结算，实际成交价优于冻结价时当场找零回可用。
- **撤单 / 拒单 / 失败 / 重试**：剩余冻结幂等释放，重复撤单或重放不会
  二次退还；`client_order_id` 相同的重试返回首单，不重复冻结。
- **恢复**：`POST /api/trading/recover` 按订单确认快照重建占用、修平漂移、
  回收孤儿冻结。
- **查询解释**：账户与持仓返回 `breakdown` 说明可用 / 占用 / 已结算差异，
  冻结流水只追加可审计。

相关接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/trading/buy`、`/sell` | 下单（可传 `client_order_id` 幂等重试） |
| POST | `/api/trading/orders/{id}/fills` | 挂起订单录入（部分）成交 |
| DELETE | `/api/trading/orders/{id}` | 撤单，幂等释放剩余冻结 |
| GET | `/api/trading/orders/{id}/freeze-events` | 单笔订单冻结/结算/释放流水 |
| GET | `/api/trading/freeze-events` | 全部冻结流水 |
| GET | `/api/trading/reservations` | 当前在途现金 / 持仓占用 |
| POST | `/api/trading/recover` | 故障恢复对账 |

真实网关（`VnpyAdapter`）下冻结以券商回报为权威（`available = 余额 - 冻结`），
本地不另立台账；完整本地冻结语义见 `SimulationAdapter`。
