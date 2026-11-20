# Legacy frontend

这里存放拆页改造前的单页前端，仅用于回溯和对照，不再由 `app.main` 的路由提供，也不作为当前产品的视觉或功能依据。

- `pages/`：旧的 home / novels / characters / periods / chat / media / models / settings 页面。
- `static/`：旧页面使用的脚本和样式。
- `assets/`：旧版三体人物图、旧登录背景和旧音频素材；新页面不引用这些文件。

当前前端在 `frontend/app/`，公共样式与脚本在 `frontend/static/app/`。新页面不依赖本目录中的任何文件。
