# 高空作业安全监控

当前版本：**0.1.0-alpha.1，工作流原型 + 可行性验证工具**。

本版尚无自动违规识别、工作服识别、高处识别或人员跟踪；所有界面事件均明确标记“人工登记”。
现有三类部件检测权重不能直接承担违规报警。95% Precision / Recall 与30 FPS是待验证目标，绝非当前成绩。

## Windows 使用

在 GitHub Actions 的成功构建页面下载 HeightSafety-windows 对应提交的产物，解压整个文件夹后运行 HeightSafety.exe。必须保留 _internal 目录。
首次运行自行创建管理员（密码至少10位），没有默认密码。
运行时不联网、不上传录像；初次安装依赖和下载程序需要联网。
测试通过的分支构建自动保存到 GitHub Releases（预发行版），包含版本标签、提交SHA和Windows完整程序包；Actions临时产物保留90天。

源码启动需要 Python 3.11：
~~~powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m safety_monitor
~~~

管理员在“管理”页添加摄像头名称、位置、RTSP地址/USB编号/本地视频。
在“实时画面”打开视频，最多4路。点击“框选人员并人工登记事件”，拖框、输入人员编号和可确认的证据。
规则判断未佩戴/佩戴不规范时发出声音，保存框选截图和前10秒、后20秒片段。
多个事件分别留档；人员编号与框选均为人工输入，红框不会自动跟随人员移动。
“事件与人工复核”可筛选、查看截图/片段、登记最终结论；管理员可导出 Excel。
每次复核均保留操作者、时间、结论和备注，不覆盖历史。

数据保存在 %LOCALAPPDATA%\HeightSafety。
离线账号权限属于应用层控制；拥有本机文件权限的人仍可访问数据库。
视频源地址（可能含摄像头凭据）保存在本机数据库，切勿把运行数据库提交公开仓库。

## 当前边界

- 视频留证宽度960像素，每路前置 JPEG 缓冲上限128MiB。启动不足10秒、停止或断流时会标记证据不完整。
- 片段为 MJPEG AVI，按时间重采样30FPS；这不代表推理达到30FPS。界面显示的是采集平均FPS。
- 工作服不确定、地面/高处不确定、遮挡或连接不清楚均进入人工复核；不把漏检当作未佩戴。
- 锚点标准尚未确定，UI维持未知；确认未挂或挂点低于工作面仍按规则判违规。
- 摄像头协议首版先接RTSP/USB，GB28181/厂商SDK待明确。断流后手动停止并重开。
- 片段时长调整仅本次会话有效。账号首版支持创建/登录/角色控制，修改密码/禁用账号待补。
- 当前无自动报警链路，不可作为现场安全保障设备。

## 模型可行性

先获取原始LFS文件（git lfs pull），然后在新目录生成修正数据：
~~~powershell
python tools/prepare_dataset.py "safety belt.zip" "runtime/dataset-v1"
~~~
脚本保留原包，修正 WH-climb 7 的0→1和 WH-work 1 的0→1、1→2；
验证图标签配对和视频源切分，生成源文件SHA256及变更计数。
必须复查框位置、遮挡标注、负样本和多人关系后才能训练。

可选 YOLO 部件检测基准（仅加载你信任的本地模型权重）：
~~~powershell
python -m pip install ultralytics
python tools/benchmark.py --model "best.pt" --video "test.mp4" --device cpu
~~~
记录模型哈希、环境、解码+检测FPS和P95延迟。不会自动下载权重。
该工具不包含跟踪和违规判断，不能替代软件端到端速度验收。

人工真值对齐后的预测 CSV 需包含 video,frame,person,truth,prediction：
~~~powershell
python tools/evaluate.py validation.csv --output runtime/evaluation.json
~~~
逐类报告 Precision/Recall，将人工复核造成的漏报计入 FN；缺少某类样本不能算通过。
仍需独立视频/场景隔离、事件级评估、误报频次、遮挡恢复以及30FPS端到端实测。

## 验证与版本

~~~powershell
python -m unittest discover -s tests -v
~~~
自动测试覆盖规则、角色权限、密码验证、复核历史、Excel公式防护、视频留证、Windows界面启动。
参见 docs/REQUIREMENTS.md 与 CHANGELOG.md。原始压缩包保持不变；每次修改使用独立Git提交。
