# roast_plugin

一个常驻桌面的 Windows AI 吐槽器。

`roast_plugin` 会观察当前前台应用、窗口标题和近期切换轨迹，在你切换窗口、长时间停留或手动触发时，调用大模型生成一句贴合当前行为的毒舌吐槽。

它不是效率助手，也不会劝你自律。它只负责坐在旁边说风凉话。

## 功能

- 自动识别当前应用、窗口标题和停留时间
- 窗口稳定切换约 1.5 秒后触发，快速切换会自动合并
- 在同一窗口停留 5、15、30、60 分钟时触发
- 保留最近约 30 分钟的活动上下文
- 支持 DeepSeek 和 OpenAI Chat Completions 兼容接口
- 轮换多种吐槽角度，并避开近期重复句式
- 常驻半透明浮窗，文字多少会自动调整大小
- 浮窗始终置顶、不会抢夺当前窗口焦点，可自由拖动
- 支持暂停、吐槽频率、立即吐槽、API 设置和退出
- API 调用失败时直接显示错误，不会伪装成模型结果

## 工作流程

```text
读取前台窗口信息
        ↓
判断窗口切换或停留节点
        ↓
整理当前标题、停留时间和近期行为路径
        ↓
调用用户配置的大模型 API
        ↓
在桌面浮窗中显示一句吐槽
```

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本

## 快速开始

```powershell
git clone <你的仓库地址>
cd roast_plugin

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python main.py
```

启动后，桌面右下区域会出现半透明浮窗。程序会在约 2 秒后根据当前窗口生成第一条吐槽。

退出程序可以：

- 右键浮窗，选择“退出”
- 右键系统托盘中的 `R` 图标，选择“退出”
- 在启动程序的终端中按一次 `Ctrl+C`

## 配置 DeepSeek

右键浮窗或系统托盘图标，选择“API 设置”，填写：

| 配置项 | 内容 |
| --- | --- |
| 接口地址 | `https://api.deepseek.com` |
| 模型 | `deepseek-chat` |
| API Key | 你自己的 DeepSeek API Key |

保存后，右键选择“立即吐槽”即可测试。成功时会显示模型生成的内容；失败时浮窗会显示 HTTP 状态码或网络错误。

也可以使用其他兼容 OpenAI Chat Completions 的服务，只需填写对应的接口地址、模型名称和 API Key。

未配置 API Key 时，程序会使用内置的本地规则文案。

## 使用方式

- **拖动浮窗**：按住鼠标左键拖动，位置会自动保存
- **立即吐槽**：忽略频率冷却，立刻根据当前窗口生成一句
- **暂停吐槽**：停止自动生成，浮窗仍然保留
- **吐槽频率**：
  - 低：两次自动吐槽至少间隔 120 秒
  - 正常：至少间隔 45 秒
  - 高：至少间隔 15 秒
- **单击托盘图标**：重新显示最近一条吐槽

## 隐私说明

`roast_plugin` 只读取：

- 当前前台应用的进程名称
- 当前窗口标题
- 应用切换顺序和停留时长

它不会读取或记录：

- 屏幕截图或屏幕录像
- 键盘输入
- 鼠标操作内容
- 文件正文
- 浏览器页面正文

配置 API 后，当前窗口标题、应用名称、停留时长和近期活动路径会发送到你填写的模型接口，用于生成吐槽。请自行确认所使用 API 服务的隐私政策。

API Key 保存在当前 Windows 用户目录下：

```text
%APPDATA%\roast_plugin\settings.json
```

该文件位于项目目录之外，不会被 Git 提交。目前 API Key 以明文形式保存在本机，请不要分享该配置文件。

## 项目结构

```text
roast_plugin/
├── main.py                   # 程序入口
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 测试依赖
├── roast_plugin/
│   ├── activity.py          # 前台窗口采集与行为触发
│   ├── app.py               # 应用控制器
│   ├── config.py            # 本地配置与旧配置迁移
│   ├── roaster.py           # LLM 调用与吐槽生成
│   └── ui.py                # 浮窗、托盘和设置界面
└── tests/
    ├── test_activity.py
    └── test_roaster.py
```

## 运行测试

```powershell
pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider
```

## 当前限制

- 仅支持 Windows
- 尚未提供安装包，需要通过 Python 启动
- 窗口标题是否有意义取决于具体应用
- 配置文件中的 API Key 尚未接入 Windows 凭据管理器

