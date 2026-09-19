<div align="center">

# HΞCKLE

### Judging every click.

一个常驻桌面、盯着你的每次点击说风凉话的 Windows AI 吐槽器。

</div>

`HECKLE` 会观察当前前台应用、窗口标题和近期切换轨迹，在窗口切换、长时间停留或手动触发时，让大模型生成一句贴合当前行为的毒舌吐槽。

视觉名称写作 **HΞCKLE**。中间的 `Ξ` 像一张抿着嘴、满脸无语的表情——正准备评价你刚才那一下。也可以想象成小萝莉皱眉（？）

它不是效率助手，也不会劝你自律。它只负责坐在旁边说风凉话。

## 特性

- 自动识别当前应用、窗口标题和停留时间
- 窗口稳定切换约 1.5 秒后触发，快速切换自动合并
- 在同一窗口停留 5、15、30、60 分钟时触发
- 保留最近约 30 分钟的活动上下文
- 支持 DeepSeek 及其他 OpenAI Chat Completions 兼容接口
- 轮换多种创作角度，并避开近期重复句式
- 常驻半透明浮窗，根据文字长度自动调整尺寸
- 始终置顶、不抢夺焦点，可自由拖动并记住位置
- 支持立即吐槽、暂停、频率调整、API 设置和退出
- API 请求失败时直接显示原因，不会伪装成模型结果

## 工作原理

```text
读取前台窗口信息
        ↓
判断窗口切换或停留节点
        ↓
整理标题、停留时间和近期行为路径
        ↓
调用用户配置的大模型 API
        ↓
在桌面浮窗中显示一句吐槽
```

HECKLE 不使用截图、OCR、键盘监听或屏幕录制。

## 系统要求

- Windows 10/11
- Python 3.10+

## 安装

```powershell
git clone https://github.com/colliderkkz/HECKLE.git
cd HECKLE

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

启动：

```powershell
python main.py
```

启动后，桌面右下区域会出现常驻的半透明浮窗。程序会在约 2 秒后根据当前窗口生成第一条吐槽。

## 配置 DeepSeek

右键浮窗或系统托盘中的 `Ξ` 图标，选择“API 设置”：

| 配置项 | 填写内容 |
| --- | --- |
| 接口地址 | `https://api.deepseek.com` |
| 模型 | `deepseek-chat` |
| API Key | 你自己的 DeepSeek API Key |

保存后选择“立即吐槽”即可验证。调用成功时会显示模型生成的吐槽；调用失败时浮窗会显示 HTTP 状态码或网络错误。

也可以使用其他兼容 OpenAI Chat Completions 的服务，只需填写对应的接口地址、模型名称和 API Key。未配置 API Key 时，HECKLE 会使用内置规则文案。

## 操作

| 操作 | 效果 |
| --- | --- |
| 左键拖动浮窗 | 移动浮窗并保存位置 |
| 右键 → 立即吐槽 | 忽略频率冷却，立即生成一句 |
| 右键 → 暂停吐槽 | 停止自动生成，浮窗仍保持显示 |
| 右键 → 吐槽频率 | 切换低、正常或高频率 |
| 单击托盘 `Ξ` 图标 | 将最近一条吐槽重新显示到前台 |
| 右键 → 退出 | 完全退出 HECKLE |

自动吐槽的最短间隔：

| 频率 | 最短间隔 |
| --- | ---: |
| 低 | 120 秒 |
| 正常 | 45 秒 |
| 高 | 15 秒 |

也可以在启动程序的终端中按一次 `Ctrl+C` 安静退出。

## 隐私与安全

HECKLE 只读取：

- 当前前台应用的进程名称
- 当前窗口标题
- 应用切换顺序和停留时长

HECKLE 不会读取或记录：

- 屏幕截图或屏幕录像
- 键盘输入
- 文件正文
- 浏览器页面正文

配置 API 后，当前窗口标题、应用名称、停留时长和近期活动路径会发送到你填写的模型接口，用于生成吐槽。请自行确认所使用 API 服务的隐私政策。

API Key 保存在当前 Windows 用户目录下：

```text
%APPDATA%\HECKLE\settings.json
```

该文件位于项目目录之外，不会被 Git 提交。目前 API Key 以明文形式保存在本机，请勿分享该配置文件或将其复制进项目目录。

## 常见问题

### 没有生成吐槽

1. 右键浮窗，选择“立即吐槽”。
2. 确认程序没有处于暂停状态。
3. 检查 API 地址、模型名和 API Key。
4. 查看浮窗显示的 HTTP 状态码或网络错误。

DeepSeek 推荐使用：

```text
接口地址：https://api.deepseek.com
模型：deepseek-chat
```

### 终端一直没有返回

这是正常现象。HECKLE 是常驻桌面程序，运行期间会持续占用当前终端。使用右键菜单中的“退出”，或按一次 `Ctrl+C` 结束。

### Windows 阻止脚本激活

可以只为当前 PowerShell 会话临时允许脚本：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

## 项目结构

```text
HECKLE/
├── main.py                   # 程序入口
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 测试依赖
├── HECKLE_MVP.md             # MVP 产品说明
├── heckle/
│   ├── activity.py          # 前台窗口采集与行为触发
│   ├── app.py               # 应用控制器
│   ├── config.py            # 本地配置与旧配置迁移
│   ├── roaster.py           # LLM 调用与吐槽生成
│   └── ui.py                # 浮窗、托盘和设置界面
└── tests/
    ├── test_activity.py
    ├── test_config.py
    └── test_roaster.py
```

## 开发与测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider
```

当前版本：`0.2.0`

## 当前限制

- 仅支持 Windows
- 尚未提供安装包，需要通过 Python 启动
- 窗口标题的可用程度取决于具体应用
- API Key 尚未接入 Windows 凭据管理器
