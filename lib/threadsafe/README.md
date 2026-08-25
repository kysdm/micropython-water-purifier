# threadsafe — 第三方组件说明

本目录为**第三方开源库**（随本项目分发，未修改核心协议）：

- **上游项目**：[peterhinch/micropython-async](https://github.com/peterhinch/micropython-async)（`v3/threadsafe/` 目录）
- **作者**：Peter Hinch
- **许可**：MIT License（见本目录 [LICENSE](LICENSE)）

各文件头均已保留上游版权声明。

## 包含组件

| 文件 | 说明 |
|---|---|
| `__init__.py` | 惰性加载器 |
| `threadsafe_queue.py` | 线程安全队列（asyncio 侧 `await`，线程侧 `get_sync` 阻塞） |
| `threadsafe_event.py` | 线程安全事件 |
| `message.py` | 线程安全消息（可携带数据的事件） |
| `context.py` | `Context`：把函数投递到另一个线程执行 |

## 本地修改（相对上游）

仅 `context.py` 有两处小改动，其余文件与上游一致：

1. `worker()` 用 `try/except` 捕获任务异常并存入 `job.rval`（原版异常会直接中断工作线程）；
2. `assign()` 检测 `job.rval` 为异常时，在调用方协程中重新抛出（原版直接返回）。

同步上游新版本时，请保留以上改动或重新应用。
