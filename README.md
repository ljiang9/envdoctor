# envdoctor

检查 `.env.example` 与代码实际引用的环境变量是否一致：**缺失**、**多余**、**未设值**，一次扫出来。

新同事 clone 项目、照着 `.env.example` 配环境，结果漏了变量导致启动崩——这类问题本该在 CI 里就被拦下来。

## 安装

纯 Python 标准库，零依赖：

```bash
git clone https://github.com/ljiang9/envdoctor.git
cd envdoctor
python -m envdoctor ./your-project
```

## 用法

```bash
python -m envdoctor ./myapp            # 扫描并打印三张表
python -m envdoctor ./myapp --strict   # 有缺失变量时 exit 1（放 CI）
python -m envdoctor ./myapp --json     # 机器可读输出
python -m envdoctor ./myapp --fix --dry-run  # 预览将要追加的变量
python -m envdoctor ./myapp --fix      # 把缺失变量追加进 .env.example
```

示例输出：

```
环境变量检查：examples/
示例文件：.env.example（5 个变量），扫描代码文件：3 个

❌ 缺失（代码用了，示例里没有）：2
  DATABSE_URL            ← config.py  ← 拼写？你是不是想写 DATABASE_URL？
  STRIPE_KEY             ← app.py

⚠️ 未设值（示例里为空，且代码使用时没给默认值）：1
  API_KEY                ← app.py, run.sh

ℹ️ 多余（示例里有，代码没用到）：1
  LEGACY_FLAG
```

三张表的含义：

| 表 | 含义 | 建议动作 |
|---|---|---|
| 缺失 | 代码引用了，示例文件里没有 | 补进 `.env.example`（或用 `--fix`） |
| 未设值 | 示例里是空值，且代码使用时没给默认值 | 填上默认值或示例值 |
| 多余 | 示例里有，代码里搜不到引用 | 确认后删除，保持示例干净 |

## 识别的引用写法

- Python：`os.environ["X"]`、`os.environ.get("X", default)`、`os.getenv(...)`
- JS/TS：`process.env.X`、`process.env["X"]`、`import.meta.env.X`、`Deno.env.get("X")`
- Go：`os.Getenv("X")`、`os.LookupEnv("X")`
- Rust：`std::env::var("X")`、`env!("X")`、`option_env!("X")`
- Shell/YAML：`${X}`、`$X`、`${X:-default}`（带默认值的不计入"未设值"）

支持 `.env.example` / `.env.sample` / `.env.template`；自动跳过 `.git`、`node_modules`、`__pycache__`、`venv` 等目录。

## 诚实说明（局限）

- **正则启发式，不是语义分析**：`os.environ.get(prefix + name)` 这类动态拼接的变量名抓不到；注释掉的代码里的引用会被误报。
- 默认值识别只看常见写法（第二个参数、`${X:-d}`），复杂表达式可能误判。
- `getenv` 裸调用（C 风格）在 Python 文件里也可能被匹配，属于可接受的噪声。
- `--fix` 只追加缺失变量，不会删除多余变量、不改现有值；追加后请人工填写真实值。

## License

MIT © 2026 ljiang9
