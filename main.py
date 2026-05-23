"""pygbag / desktop 入口。
pygbag 的运行时模板写死了找 main.py, 所以这里做一个薄壳, 委托给 metro.main()。
桌面运行 `python3 main.py` 或 `python3 metro.py` 效果相同。
"""
import asyncio

import metro

if __name__ == "__main__":
    asyncio.run(metro.main())
