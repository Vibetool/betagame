"""pygbag / desktop 入口。

pygbag 的运行时模板硬编码了寻找 assets/main.py 作为脚本入口,
所以这里做一个薄壳, 委托给 metro.main()。

注意: 不要把 asyncio.run 包在 `if __name__ == "__main__":` 里 —
pygbag 在加载 main.py 时会改写顶层的 `asyncio.run(...)` 让它不阻塞,
一旦套进 if 块, 这个改写可能错过, 导致 WASM 端永远卡在 Loading。
"""
import asyncio
import sys

print("[main.py] starting", flush=True)
sys.stdout.flush()

import metro

print("[main.py] metro imported, entering game loop", flush=True)
sys.stdout.flush()

asyncio.run(metro.main())
