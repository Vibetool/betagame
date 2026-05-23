"""pygbag / desktop 入口。"""
import asyncio
import sys
import traceback

# 用 document.title 当诊断通道, 不依赖 console
def _trace(stage):
    print(f"[main.py] {stage}", flush=True)
    sys.stdout.flush()
    try:
        import platform as _p
        _p.window.document.title = f"booting: {stage}"
    except Exception:
        pass

_trace("starting")

try:
    import pygame  # noqa: F401  -- 在 pygbag 里这个会触发解释器+SDL2 加载
    _trace("pygame imported")
    import metro
    _trace("metro imported")
    asyncio.run(metro.main())
except Exception as e:
    _trace(f"FATAL: {type(e).__name__}: {e}")
    traceback.print_exc()
    raise
