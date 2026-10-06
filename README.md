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

## 资金 / 持仓冻结机制

`app/trading/ledger.py` 的 `FreezeLedger` 用「不可变冻结记录 + 剩余额度 +
审计流水」跟踪每笔委托占用的资源，所有变动在同一把锁内原子完成：

- **提交确认**：买入冻结现金（限价单按限价，市价单按保护价 `market_protect_ratio`，
  默认 +3%，并预留预估费用），卖出冻结可用持仓；冻结规则写入订单快照
  （`freeze_rule` / `frozen_amount` / `frozen_quantity`），确认后不变。
- **成交**：冻结转已结算；支持部分成交、多次回报，成交数量超过剩余委托会被
  拒绝，杜绝重复结算。买入从冻结现金扣款，卖出净收入（货款 - 税费）回可用。
- **撤单 / 拒单 / 失败**：仅释放剩余冻结，释放幂等，重复撤单、重复回报不会
  重复释放。部分成交后撤单只释放未成交部分。
- **重试**：`POST /api/trading/orders/{id}/retry` 先幂等释放旧冻结，再按新
  价格重新固定规则，旧记录归档可审计。
- **恢复**：`recover_orders()` 按 SUBMITTED / PARTIAL_FILLED 委托的剩余数量
  重建冻结，重复恢复幂等。
- **并发**：下单支持 `client_order_id` 幂等单号；同一资源的校验与占用在锁内
  原子完成，并发请求不会出现负余额或重复承诺。

恒等式（`GET /api/trading/freeze/report` 实时校验）：

```
现金：available_cash + frozen_cash + settled_cash_net = initial_cash
持仓：quantity = available_quantity + frozen_quantity（T+1 在途买入另计）
```

相关接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/trading/buy`、`/sell` | 下单（可传 `client_order_id` 幂等） |
| DELETE | `/api/trading/orders/{id}` | 撤单（允许部分成交后撤剩余） |
| POST | `/api/trading/orders/{id}/retry` | 释放旧冻结后重试 |
| GET | `/api/trading/freeze/report` | 可用/冻结/已结算差异解释与守恒校验 |
| GET | `/api/trading/freeze/moves` | 冻结/结算/释放审计流水 |

