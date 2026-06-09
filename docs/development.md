# 开发说明

## 环境要求

- Python 3.10+
- Node.js 18+

## 安装

后端：

```powershell
python -m pip install -e .
```

前端：

```powershell
cd web
npm install
cd ..
```

创建本地配置：

```powershell
Copy-Item .env.example .env
```

## 启动

Windows 一键启动：

```powershell
.\start.ps1
```

手动启动后端：

```powershell
python main.py
```

手动启动前端：

```powershell
cd web
npm run dev
```

默认地址：

- API：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 前端：`http://localhost:5173`

## 测试

后端：

```powershell
python -m pytest
```

知识库和配置相关快速测试：

```powershell
python -m pytest tests/test_imports.py tests/test_config_api_fields.py tests/knowledge -q
```

前端构建：

```powershell
cd web
npm run build
```

## 提交前检查

```powershell
git status --short
git ls-files data web/knowledge .env
```

确认不要把 `.env`、数据库、日志、个人知识库和交易记录提交到 GitHub。
