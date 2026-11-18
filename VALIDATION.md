# 本次功能与界面验收

最新正式版本：0.4.3，worker revision 20，源码与包内回归各 539 项、Godot 边界 254 项。较早章节保留为历史记录。

## 2026-11-18 v0.4.3 持续自动分解、材料开关与穿戴保护

独立分解增加保存偏好的“自动分解”开关，持续重新评估后续掉落，自动成长暂停时同样运行。手动预览／一次性执行继续保留，但自动模式开启时拒绝并行手动执行。停止独立分解会关闭该开关，已提交请求继续核验；正常成长中的“换装后分解”由原模块开关单独控制。

“材料参与分解”默认关闭，并同时作用于正常成长、独立自动及手动分解。Python 候选和 Godot 报价／执行前均检查许可；材料、品质或交易设置变化会使旧手动预览失效，关闭材料后旧混合报价不能继续执行。明确开启材料后仍保护当前／下一阶配方材料、锁定等。

穿戴保护按全部角色的 `equipped_equipment_ids_by_char` 与已穿戴魔石映射检查，即使原物品的 `state_flag=0` 仍拒绝报价与分解。品质许可、材料开关和允许可交易都不能覆盖此保护。没有为验证故意卸下装备或消费英雄品质装备。

同时补齐镶嵌预算：桥接调用游戏原生 `gem_socket_policy.apply_gold_cost()` 导出成本，Python 在卸装前和操作阶段检查金币、成长储备及扩容预算，Godot 实际提交时再次读取原生成本／金币。成本未知、机会快照过期或预算不足时不卸装；卸装后条件变化先恢复装备。仅复用原生方法，发布包不含游戏源码或成本算法。

- 539 项源码回归与相同最终 EXE 的 539 项包内自检通过；Godot 254 项边界通过，其中消费 91、连接 33、加载 130。包含真实调度／`_execute` 提交路径中的默认材料保护、旧报价拒绝、其他角色穿戴与镶嵌预算变化检查。Vite 与 PyInstaller 构建通过。
- 当前 xsjsteam 会话的 revision 20 成本机会中有 29 个装备目标、145 组装备／宝石成本。已穿戴魔杖 55238396 的原生成本为 4000 金币，头盔 167013221 为 16000；此项验证原生成本导出，不把它写成镶嵌消费成功。
- 在成长暂停、独立自动关闭时，材料关闭预览为 0 条，30 件全角色穿戴装备受保护。临时开启材料仅预览出 2 条旧材料，4 条当前／下一阶配方材料保留；没有执行材料分解。随后通过页面关闭材料，旧预览立即清空。原材料记录数量未减少，期间金币／战斗材料存在被动增长；穿戴映射完全一致。
- 通过页面开启独立自动，成长继续暂停；15 次连续采样均保持材料关闭、独立自动开启且未发起其他模块操作，无候选时显示等待。通过“停止独立分解”验证 `auto_salvage=false` 已保存且正常 inventory 模块设置保持。
- 随后临时关闭正常成长的 inventory 模块，独立自动保持开启、材料保持关闭，再恢复成长；两分钟 60 次采样中完成 3 轮原生分解，共消费 5 件品质 1–2 的剩余装备。逐条原生成功回执的 `consumed_item_ids` 均对应采样中的装备、未命中材料记录或任何角色穿戴映射，最后从权威库存消失；30 件穿戴装备映射全程不变。这证明本次清理由独立自动模式执行，后续掉落能够重新评估。
- 测试结束已恢复全部 16 个成长模块、自动成长及 `auto_start=true`；独立自动分解开启、材料关闭、允许可交易且仅品质 1–4、自动重连关闭。8 次连续采样连接与运行正常。仅正常更新助手，游戏 PID 144188、创建时间 1794951333.7777767 保持；部署前后实例配置校验一致，后续上述临时设置均经明确验证和恢复。
- 1440px 与 390px 布局无整页横向溢出，独立分解面板截图已逐张查看，无文字裁切或控件重叠，控制台 0 errors／0 warnings。截图为 `output/playwright/materials-auto-desktop.png` 与 `materials-auto-mobile.png`。
- 正式／沙盒 EXE SHA-256：`42f86c9a4c42d4c516217de06b80cafed6eec5f5ca732d6a65241e2a7cf8e021`。ZIP 16,153,237 字节，SHA-256：`714e195a2a3e62750859082e27fb14773f520ab671a84bd011c3b46248373a8c`；10 文件白名单、CRC 与载荷哈希校验通过。发布附件为 `auto_IdleHero-v0.4.3-windows-x64.zip` 和 `SHA256SUMS.txt`。

改前源码、旧 0.4.2 EXE 与本轮证据保存在忽略目录 `.private/socket-budget-20261118/`。`original/` 为修改前文件，`deploy/account-at-deploy/` 为部署时账号配置／调度备份，`independent-live-proof.json` 汇总原生回执与消费核验，`final-state.json` 与 `final-connection-samples.json` 为恢复运行后的记录。回滚前关闭独立自动并暂停成长，等待结算与维护结束，使用 `--stop` 正常退出助手，再还原 `original/dist/` 中旧 EXE 和校验文件；保留当前账号配置／调度记录，配置备份仅用于逐项核对。源码可从 Git v0.4.2 恢复。

当前单会话短时样本不能代表长期、多账号或所有后期系统。强化仍等待游戏原生开放，其他账号、新号至后期及全部成长系统的完整实机验收尚未完成；原总目标保持 active。

## 2026-11-18 成长阻塞、满包开箱与独立分解

技能成本 200501 属于角色技能点，原策略误从普通材料背包读取，导致已有点数的技能无法进入队列。现从 `inventory.character_progress_by_char[owner].skill_points` 读取，Python 规划与 Godot 实际提交前均校验所属角色、即时点数、重复费用合计与混合材料成本，其他角色点数不能代付。

昂贵扩容买不起时，原策略预留全部金币并挤占星座等成长预算。现按 `capacity_saving_ratio` 默认积攒可用金币的 25%；扩容已经买得起时仍完整保护成本。背包压力期间，清理、图鉴、鉴定、换装与扩容优先于常规邮件／副本，暂停继续制造占位物品。16 个模块分别显示当前资源、原生前置或保护原因。

独立分解提供预览、执行、停止，自动成长暂停时同样可用，且不会因此开启其他模块。预览两分钟内有效且仅使用一次，绑定当前账号、PID、品质、交易许可及候选集合；新掉落不追加，保护状态变化时重新检查。沿用原生报价编号、单请求调度、成功回执与权威库存变化核验；停止后已提交请求继续核验，助手重启只恢复既有 pending，不重新启动整个清理任务。

- 当前用户明确允许可交易且英雄以下的分解；本实例设置为 `salvage_allow_tradeable=true`、`salvage_grades=[1,2,3,4]`，英雄品质 5 及以上保留。新实例默认仍保护可交易物品。已穿戴、锁定、仓库、未鉴定、强化／镶嵌投入、必要备用和配方材料继续保护，交易信息未知时等待。
- 源码与相同最终 EXE 内各 506 项隔离回归通过；独立 Godot 检查 237 项通过，其中消费边界 74 项、连接 33 项、加载 130 项。Vite 与 PyInstaller 构建通过；新增角色点数、真实 `_execute` 路径、交易许可、品质／投入边界、一次性预览及暂停独立执行回归。
- 当前 xsjsteam 真实会话在自动成长暂停时，独立分解的 33 件预览装备均取得原生成功回执并从权威库存消失，背包 50/50→20/50，原有英雄及以上装备保留。随后恢复成长，待领奖励 30→0，梦学星 I 4→5；技能学习、升级与魔方制造有成功记录。证据窗口内技能点 ayu 12→10、hiro 14→9、peach 14→10，后续可继续正常消费。
- 最终页面再次操作预览→执行→停止，停止时仅提交报价、清理 0/10 条，任务停止且旧预览执行按钮禁用；随后通过页面恢复自动成长。1440px 与 390px 视口无整页横向溢出，控制台 0 errors／0 warnings。截图保存在 `output/playwright/final-salvage-desktop.png`、`output/playwright/final-salvage-mobile.png`。
- 最终部署仅正常停止并重启助手，游戏 PID 144188、创建时间 1794951333.7777767 保持不变；部署核对各实例配置 SHA-256 不变，临时暂停后已恢复运行。8 次连续采样全部连接正常、自动成长开启、快照年龄不超过 2.062 秒，HTTP 约 4.89–95.31 ms；最后背包 18/50，自动重连关闭，品质与交易许可设置保持。此为当前单实例短时样本，不代表长期或多账号表现。
- 正式／沙盒 EXE SHA-256：`88eae464a525d0155b56527cbb90504971fcab89708b6cf6443265cce9a3582c`。ZIP 16,138,591 字节，SHA-256：`0925a93b141384649e1c56c0984bad5810d4e58f4f6b4a304fb4126bee6bf694`；10 个白名单文件的 ZIP CRC 与清单内容校验通过，含 506 项包内报告。发布附件名 `auto_IdleHero-v0.4.2-windows-x64.zip`，外附 `SHA256SUMS.txt`。

改前源码、0.4.1 EXE、账号配置／调度备份与全部实机证据位于忽略目录 `.private/growth-fix-20261118-141338/`。`live-evidence.json` 汇总清理和成长证据，`final-deploy/deployed.json` 记录最终部署身份／配置检查，`final-connection-samples.json` 与 `final-state.json` 记录恢复运行后的采样。回滚时先暂停并等待结算结束，使用 `--stop` 正常退出助手，再还原 `original/dist/` 中两个旧 EXE 与原校验文件；保留当前账号配置／调度记录，备份仅供逐项核对，不盲目覆盖。源码可从本目录 `original/` 或 Git v0.4.1 恢复。

强化当前原生仅提供 `highest_cleared_map_id=500137`，没有可用的解锁条件／就绪标记，页面明确等待原生开放，没有绕过。其他未解锁／资源不足系统、多个真实 Steam 账号并发、新号到大后期与断线长跑仍未完成完整实机验收；隔离回归不能代替这些实机结算证据。原目标保持 active。

## 2026-11-17 旧实例选择造成的假断线修复

根因：选中实例的游戏进程已经退出，但 Manager 继续保留其选择与历史 PID；同一环境积累多个历史记录时，新进程又生成独立实例，页面没有自动切换到实际在线且已连接的实例。旧页面因此显示未连接，另一个实例卡片却显示已连接。

修复后，同一环境只有一个运行实例时自动跟随；新 PID 可复用选中离线实例的配置目录，保留暂停与参数。多个实时 PID 时不猜测，手动查看离线实例时保持选择。卡片显示退出状态与历史 PID，连接判定必须匹配当前进程身份和新鲜快照，切换期间拒绝旧缓存。

- 新增 15 项回归，覆盖截图中的多个历史 PID 与在线暂停实例、独立配置、助手重启、游戏立即或隔时换 PID、助手与游戏同时重启、缓存拒收、手动离线选择、跨环境边界、同环境多个实时 PID 和先开助手后开游戏。源码及 EXE 包内完整场景均为 459 项，通过。
- 独立桥接边界 220 项及 Vite/PyInstaller 构建通过。worker 保持 revision 18。
- 正常停止并更新助手后，实机仍连接同一个游戏 PID 140420，进程创建时间不变；各实例配置 SHA-256 保持，当前实例暂停、无 pending 或维护事务。未重新启动游戏，也未强制执行消费操作。
- 正式与沙盒版 EXE SHA-256：`ccaf4af99d252b843c614e544ae6bf27e4516fefeec9b4707ae21980292dda63`；分发 ZIP 16,111,619 字节，SHA-256：`12acd5bd9bf4c2bd6f78bcb9ce636591b5ac5d43d1c371c64e1d5cbddb32bd3a`。10 个文件的 ZIP CRC、大小和 SHA-256 通过，含 459 项包内报告。
- 修改前的源码、EXE、注册表文件及实例配置/调度备份在 `.private/connection-fix-20261117/`，部署核验为 `deployed.json`。回滚前正常停止助手，再还原 `original/dist/` 中两个 EXE 与 SHA256.json；如需恢复源码，使用相应 `original/` 文件。保留当前账号配置，配置备份仅供逐项核对。

本轮没有为了验证而退出并重启真实游戏；换 PID 的组合场景由隔离回归覆盖。历史的多账号、长期断线、新号至后期验收边界保持。

## 2026-11-17 GitHub 发布复核

重新执行 444 项源码回归和从最终 ZIP 提取的实际发布 EXE 的 444 项隔离自检，完整场景与 ZIP 中附带的报告一致。220 项 Godot 桥接边界检查（57 项消费、33 项连接、130 项加载）及 Vite 生产构建通过。未修改程序行为，沿用 2026-11-16 构建的 worker revision 18。

发布附件名为 `auto_IdleHero-v0.4.0-windows-x64.zip`，与本地 `dist/挂币英雄全程全自动版-20261116.zip` 逐字节相同。ZIP 中恰有 10 个白名单文件，CRC、文件大小和 SHA-256 全部通过；ZIP 大小 16,103,083 字节，SHA-256 为 `2143842c6cbc6d7d5e8edc0bdf2e8ce2599e5511f1ad6f824122aa616cb6edad`。程序 SHA-256 为 `fedbbc45011f05fef28b3cc917f5dc30c835bb1425432d40f741a9a332fbe127`。本次为发布复核，实机验收范围沿用下一节记录。

## 2026-11-16 连接与多实例维护

- 444 项源码回归和 444 项发布 EXE 包内自检通过，覆盖 16 个成长模块既有策略及本轮新增的实例隔离、并行调度、恢复与缓存行为。报告：`runtime/self-test.json`、`runtime/packaged-self-test-candidate.json`。
- 自有桥接独立语法、220 项边界检查，以及 PID 独立目录创建和快照实际写入检查通过。未使用逆向工具；本轮沿用现有原生接口。需要进一步逆向时按用户要求使用 IDA。
- 本机与沙盒两个调度器可各自保持一个待结算请求，账号回执不能跨实例核验；同一沙盒两个不同 PID 分别绑定独立目录。此项为隔离回归，不是两个 Steam 账号的实机同时运行记录。
- 首次启动、游戏缺席和明确终止状态均受自动重连开关限制，默认关闭。升级当前配置时关闭该选项；当前自动化保留暂停。16 个网页模块开关全部执行关闭与恢复开启，保存生效；重新检测按钮、桌面和 390px 窄屏布局通过，浏览器无错误或警告。
- 现有游戏 PID 127696 保持不变，没有结束或重新启动游戏。实机环境为 xsjsteam，buildid 26636673，原生日志版本 v1.11.205。当前原生会话连接正常、桥接 revision 18。
- 实机执行一次只读邮件列表同步，收到原生回执并核验成功，随后恢复完整原模块配置。测试记录：`runtime/native-mail-final.json`。显示设置中，特效关闭与恢复、15 FPS 生效及关闭性能模式恢复 60 FPS 均通过，随后恢复测试前的 10 FPS 性能设置，见 `runtime/display-final.json`。
- 8 次连续 HTTP 采样全部连接正常，快照年龄约 1.7 至 2.1 秒，HTTP 响应约 4 至 14 毫秒，见 `runtime/live-performance-final.json`。游戏快照从约 5.95 MB 降到约 0.293 MB。
- 助手 worker 进程短时抽样：修改前约占单个 CPU 核心 61.24%，RSS 187.4 MiB；修改后约 2.19%，RSS 81.81 MiB。两次均为当前单实例暂停自动化状态的短时样本，不能推导多开或长期负载，见 `runtime/helper-resource-final.json`。
- Word 启动教程用原生 Word 导出后，通过文档渲染器生成 4 页 PNG 并逐页检查，未见裁切、重叠、空白页或缺字。渲染文件仅作 QA，不放入分发包。
- 正式 EXE 与沙盒版 EXE 均与通过自检的候选完全一致，SHA-256 为 `fedbbc45011f05fef28b3cc917f5dc30c835bb1425432d40f741a9a332fbe127`。最终分发包 `dist/桌面勇者自动远征-多实例版-20261116.zip` 共 10 个白名单文件，ZIP CRC 和内置文件 SHA-256 全部通过；仅包含自有助手、教程、使用说明与测试报告。ZIP 为 16,103,083 字节，SHA-256 为 `2143842c6cbc6d7d5e8edc0bdf2e8ce2599e5511f1ad6f824122aa616cb6edad`，记录见 `runtime/package-20261116-manifest.json`。

### 功能覆盖边界

本轮实机核验了当前沙盒接入、状态刷新、只读邮件回执、16 个网页模块开关、配置保存和显示选项。所有成长模块策略、资源保护、未知结果隔离和恢复分支由隔离回归覆盖。没有为验证而强制消费金币、强化装备或切换账号；本机多账号与多个沙盒账号同时运行、未解锁和资源不足分支仍需对应真实条件下的后续实机验收。不能把回归通过写成全部功能均已现场消费成功。

日期：2026-11-09。参考凡修工作台；采用官方 Fluent UI。每项参数均在对应开关下方。修改前的源码位于 `runtime/before-reference-ui/` 与 `runtime/before-final-feature-check/`。

- 52 项回归场景通过，报告：`runtime/self-test.json`。
- 打包 EXE 内自检同样 52 项通过：`runtime/packaged-self-test.json`。
- 自有桥接独立 Godot 语法加载通过；实机 worker revision 6，游戏进程保持连接。
- 六项核心开关通过实际页面操作分别关闭、开启并核对服务配置。
- 最低换装提升保存 3.5%，非法 -1 输入被拒绝，恢复 2.5%。
- 品质筛选与星座优先级通过实际页面往返修改，已恢复默认。
- 性能模式实机快照上限变为 10 FPS；关闭后恢复 60 FPS。
- 极简特效关闭后 hidden_layers=0，重新开启后 hidden_layers=2。
- 外部写入带 BOM 配置，将 FPS 改为 15，5 秒重载链路实机生效；现已恢复默认。
- F8/F9/F10 注册成功，切换逻辑经隔离测试验证。
- 品质保护和运行日志按钮交互通过；控制台没有 JavaScript 错误。
- 实机核验原始记录：`runtime/final-feature-check.json`。

修正了当前原生版本中技能学会后自动生效的兼容问题，避免反复请求已经禁用的装槽接口。星座节点必须在回执后观察到等级更新，才核验成功。

以上不替代从新账号到大后期的持续实机验收。150 级与副本 100 层仅为隔离调度场景，不能视为账号实机已达到该阶段。

## 2026-11-10 持续调度复核

- 实际回执发现技能预览 `ok=true`、`can_afford=false` 时仍提交升级，服务器返回 `ItemNotEnough`。现已同时在策略和桥接执行前检查可支付状态。
- 新版 EXE 启动后连续 6 次观测、跨度约 25 秒，连接持续正常，未新增技能升级拒绝或调度异常；当前主线为 500117。原始记录为 `runtime/continuous-growth-observation.json`。
- 修正最强戒指已穿戴时阻止另一枚弱戒指替换的问题；零魔石槽不再中断全局规划；副本换楼层仍遵守挑战间隔。
- 暂停总开关或关闭强化模块时，未完成维护转为恢复装备，不继续发起维护消费。
- 验证带 BOM 配置在启动首轮生效，避免重载前误用默认值。
- 实际页面核对 16 项成长功能和 2 项显示功能，参数区域均在对应开关下方，无横向溢出；浏览器错误数为 0。页面截图：`runtime/continuous-growth-ui.png`。
- 此次修改前备份：`runtime/before-continuous-growth-20261109-235953/`，包含源码与旧 EXE。

## 2026-11-10 容量联动发布复核

- 源码及单 EXE 内自检均为 69 项通过；加入扩容前置、资源等待、满级、关闭模块、魔石/宝箱压力、制造预算和双戒指制造场景。
- 新 EXE 实际启动并连接原游戏会话；F8/F9/F10 均注册成功，自动成长保持开启。
- 页面实测容量联动开关关闭与开启均保存到服务配置，最后恢复默认开启和 85% 阈值。
- 页面核对 16 项成长功能、2 项显示功能，以及立即巡检、品质保护、配置文件、运行日志。18 项参数容器均位于对应开关下方。
- 1440 像素和 390 像素视口无整页横向溢出；重新打开新版页面后控制台错误数为 0。
- 界面截图：`runtime/capacity-complete-ui.png`；发布校验与连接记录：`runtime/capacity-release-check.json`。修改前备份：`runtime/before-capacity-review-20261110-001207/`。
- 容量资源门槛和前置链在隔离场景验证；尚未观察当前账号实际触发扩容，更不代表新号到大后期的完整实机验收。原目标继续保持未完成。

## 2026-11-10 背包回收与报价边界

- 装备保留改为按全部已有角色实际等级分配可穿戴装备、双戒指和有限备用。150 级多阶段背包属于隔离回归场景，不能当作实机后期证据。
- 图鉴只保留本轮可登记候选，关闭图鉴后其候选不会永久阻塞清理。实机三条图鉴登记成功证据见 `runtime/roster-inventory-live.json`。
- 修正 Godot JSON 数值白名单：JSON 数字为浮点，`Array.has(int)` 会拒绝等值品质；改为逐项整数比较。
- 分解执行绑定进程、原生报价 request_id 与物品清单，桥接执行前再核对。旧报价在 worker 热更新后被拒绝为 `salvage_quote_changed`，随后自动重新报价并成功执行。
- 实机进程 17592 的分解操作 `49d727737a08499dad6908162fde1950` 收到 request_id 164 成功回执，`consumed_item_ids=[46019963,46020026]`。两件装备从权威库存消失，背包 17/23 → 15/23，所有已穿戴 ID 保持不变。证据：`runtime/quote-boundary-release-check.json`。
- 断线回执若标明 `outcome_unknown` 或 `transport_lost`，保留未知结果；隔离该报价上下文，避免把所有后续分解停用一天。旧操作 `b5b0e8f085ce4fbf8ad28d96500e2ba6` 的断线记录仍保留，未标成成功。
- 最新源码和打包 EXE 内各 96 项回归通过；自有桥接在独立 Godot 4.8 dev 中通过 15 项品质保护与报价边界检查。独立引擎检查不能替代游戏 Godot 4.7.2 实机结算。
- 最新 EXE 实际运行，worker revision 9 已热加载到同一游戏进程 17592，默认 16 项成长模块全部开启；F8/F9/F10 注册成功，页面无横向溢出、浏览器控制台错误为 0。
- 副本入口核验改用即时快照与原生入口结果，给予异步切图 10 秒确认窗口。奖励容量满或会话未就绪时等待；本轮实际入场结果另行记录，不据隔离测试宣称后期副本已通过。
- 副本真实入场记录：操作 `1d7b395285dc40cf96c557f2eaf6e132` 返回 `ok=true`、`entered_map_id=500201`、`in_dungeon=true`；随后原生战斗结算并返回主线，主线继续推进。证据：`runtime/dungeon-live-evidence.json`。这只证明当前已解锁的第 1 层闭环，不代表全部副本楼层或大后期已验收。
- 修改前备份：`runtime/before-quote-boundary-20261110-011735/` 与 `runtime/before-dungeon-observation-20261110-012115/`。

## 2026-11-10 魔石合成候选边界

- 原因复现：策略允许 `state_flag=1` 的候选，桥接 `_consumable_instance()` 拒绝同一批 ID，实机日志出现 `合成魔石 · ... · protected_stone`。
- 修复后策略同时排除 `1|2|4|8|32|64`，并检查候选存在性、唯一性、同一 `item_data_id` 和合成结果配方。
- 桥接机会导出增加即时快照过滤，已装备、不存在、跨配方或受保护 ID 不再写入 `opportunities.stone_merge_ids`。
- `python -X utf8 tools\self_test.py`：`107/107`；`python -X utf8 tools\validate_bridge.py`：`17/17`；候选 EXE 自检：`107/107`。
- 正式 EXE SHA-256：`9ba366cbed405038867e10bfed9ecbdee5d890ab5eaba4ab3818ecbb1413b234`，记录于 `dist/SHA256.json`。
- 助手旧进程已正常停止并重启，游戏未停止，当前 PID `2028`；03:11:02 后没有新的 `stone_merge`/`protected_stone` 日志，快照仍为 `connected=true`、`phase=ready`。
- 修改前备份：`runtime/before-stone-merge-cleanup-20261110-030640/`、`runtime/before-formal-stone-merge-deploy-20261110-031025/`。

## 2026-11-10 机会快照同步复核

- 发现第一次部署后首轮仍会读取旧机会文件，虽未超过 15 秒绝对年龄，但已落后当前库存快照；调度器现在要求机会导出与当前快照差值不超过 8 秒。
- `opportunities_ready()` 回归覆盖跨快照拒绝和同步快照放行；源码回归 `109/109`，候选包自检 `109/109`。
- 第二次正式 EXE SHA-256：`ee55ca225ca48757af02b4f9d486e53fb678d80fded77158fad1ce295c4076dd`，正式/候选文件一致；记录于 `dist/SHA256.json` 与 `dist/SHA256-candidate.json`。
- 正式助手 03:20:14 重启，游戏未停止，PID `2028` 保持 `connected=true`/`phase=ready`；观察窗口内魔石合成成功回执 2 次，`protected_stone` 新增 0 次。
- 当前机会快照年龄约 3 秒，说明桥接导出与调度器读取正常同步。
- 第二次部署备份：`runtime/before-formal-stone-merge-sync-deploy-20261110-031934/`。

仍待完成：跨账号开箱即用、全新账号到大后期的完整持续实机流程，以及各后期玩法的实际结算与联动验收。目标保持 active。

## 2026-11-10 无请求号动作确认复核

- `python -X utf8 tools\self_test.py`：103 项回归场景通过，报告为 `runtime/self-test.json`。
- `python -X utf8 tools\validate_bridge.py`：Godot 独立桥接语法与 17 项检查通过。
- `npm run build`：Vite 生产构建通过。
- `python -X utf8 tools\build_release.py --candidate`：候选单 EXE 构建通过，文件为 `dist/桌面勇者自动远征-候选.exe`，摘要为 `dist/SHA256-candidate.json`。
- 原生 `loot_claim` 无 `request_id` 时，先保持 pending，待 `opportunities.loot.count` 低于动作记录的 `loot_before` 才计成功；45 秒内未变化不会立即重复消费。
- 原生 `consumable_exp` 无 `request_id` 时，先保持 pending，待 `snapshot.consumables.exp_scroll_enabled` 或 `exp_scroll_active` 变为真才计成功。
- 自检覆盖两类动作的“未变化等待”和“状态变化成功”路径；成功计数断言使用每个新引擎实例的基线，兼容持久化 scheduler 状态。

上一轮正式 EXE 当时由两个助手进程占用，因此未覆盖正在运行的 `dist/桌面勇者自动远征.exe`；本轮已通过 `--stop` 正常停止助手、备份旧文件并完成正式包替换。

## 2026-11-10 垃圾装备清理修复

- `protected_items()` 现在按已拥有角色的实际槽位分配装备；未拥有角色（含未启用 DLC）的职业专属武器不再因“没有 owner”而永久保护。
- 背包占用达到 85% 时，配置的备用装备数量临时降为 0；已装备、锁定、仓库、未鉴定、强化/镶嵌投入、图鉴当轮候选、下一阶段和有限远期装备仍受保护。
- 新增两项回归：未拥有职业武器可进入分解报价；高容量时释放备用垃圾。源码自检 `103/103`，候选包内置自检 `103/103`。
- 独立 Godot 桥接检查 `17/17`；部署 `bridge/worker.gd` 后，材料记录（`material_records`）可用于图鉴登记但不会进入分解。
- 正式 EXE 重启接回游戏 PID `2028` 后，自动报价并执行 `cube.convert`，原生回执消费 `[46058757, 46098667, 48190726]`，背包 `21/26 -> 18/26`；已装备物品未被消费。
- 同一实机观察中，祖母绿/紫水晶登记从 `protected_collection_item` 恢复为成功结算。此记录只覆盖当前账号和当前解锁状态，不替代新号到大后期、跨账号、断线重启长跑验收。

## 2026-11-10 自动开启持久化与正式包部署

- 源码自检：`110/110`；独立 Godot 桥接检查：`17/17`；`npm run build` 通过；候选包内置自检：`110/110`。
- 候选包 `dist/桌面勇者自动远征-候选.exe` 的 SHA-256 与正式包一致：`0e103b44cbd41fed787572068b875a187806007d5deec85fc92d74b9d9a16c07`；正式校验清单为 `dist/SHA256.json`。
- 正式 EXE 替换前备份：`runtime/before-junk-auto-persist-deploy-20261110-035928/`。
- 持久配置文件 `%LOCALAPPDATA%/WalletHeroesAssistant/config.json` 实测 `auto_start=true`、16/16 模块开启、`spare_copies=0`；因此下次启动助手会恢复自动成长状态。
- 游戏快照新鲜度约 0.8 秒，仍为 `connected=true`、`phase=ready`、PID `2028`。本次没有重启游戏。
- 助手/API 当前未运行。尝试从受支持的桌面启动接口启动时收到 `USER_CONTROL`，因此未绕过控制锁另起进程；Chrome 中工作台显示“本机服务暂时不可用”。本记录不能作为部署后调度器已恢复运行的证据。
- 当前账号 5 件装备回收已收到原生成功回执，回收候选为 0、背包 `12/27`；详细 ID 见 `MODLOG.md`。

仍待验证：助手重新启动后 API/工作台状态、跨账号开箱即用、新号到大后期、后期玩法实际结算及断线重启长跑。

## 2026-11-10 助手恢复后实机复核

- 正式 EXE 已启动；父进程 PID `34920`、本机 HTTP 服务子进程 PID `2600`，`127.0.0.1:17470/api/state` 可读。
- API 返回 `running=true`、`connected=true`、状态“自动成长中”；配置仍为 `auto_start=true`、16/16 模块开启、`spare_copies=0`。
- `/api/state` 与实时桥接快照均指向游戏 PID `2028`，快照 `phase=ready`；实际仅有一个目标游戏进程，本次未重启游戏。
- 恢复后观测到原生分解结算和两次技能升级成功，成功计数从 `415` 增至 `418`；背包为 `12/27`，无挂起请求。
- 因此本轮“单击助手恢复自动化且保留现有游戏会话”通过；完整新号到大后期、不同账号覆盖和长时间断线恢复仍未验证。

## 2026-11-10 冷启动分支与连续成长

- 重新核验 API：`running=true`、`connected=true`、`auto_start=true`、16/16 模块开启、`pending=null`。
- 当前权威快照的角色等级为 `ayu=21`、`hiro=18`、`peach=18`；主线最高通关 `500122`、当前战斗地图 `500123`，成功计数 `435`，无挂起请求。
- 历史 `sim.player.level` 样本在 18/21 间交替，视为场景字段而非角色等级单调曲线；等级验收使用 `character_progress_by_char`，不把采样切换误记为成长或回退。
- 隔离模拟 `runtime.launch()`：目标游戏不存在时对配置游戏 EXE 发起一次 `Popen`；目标游戏已运行时返回 `False` 且不重复启动。测试没有创建实际游戏进程。
- 当前会话验证了单击助手复用已运行游戏；因避免打断进度，未关闭游戏进行真实冷启动验收。跨账号、新号到大后期及长时间断线恢复仍未通过实机验证。

## 2026-11-10 合成拒绝退避与自动化持久化

- `protected_stone` 拒绝后，所有魔石合成候选进入 30 秒统一冷却；其他成长动作不受影响。
- 助手 `/api/stop` 只停止本地助手，不再把自动化偏好改为关闭；手动暂停仍会保存 `auto_start=false`。
- 回归 `113/113`，候选 EXE 内置自检 `113/113`，Godot 桥接检查 `17/17`，前端生产构建通过。
- 正式 EXE SHA-256：`ccb58205c33703ed45ee2087670713dff74bb23a2198b8253524e98927b6d417`；发布前文件、配置与校验清单备份在 `.private/backups/stone-merge-cooldown-20261110/`。
- 实机 API `running=true`、`connected=true`、`auto_start=true`，16/16 模块开启。游戏 PID `2028` 及启动时间未变；本次只重启助手。
- 旧装备有成功分解记录；当前 13 个原生可分解候选均为制造材料，且都被现有制造配方引用，因此继续保留。当前背包 `14/27`，没有符合策略的闲置装备回收候选。
- 候选版本恢复后观察到 1 次 `protected_stone` 拒绝（单一 operation ID），之后没有第二次魔石合成提交；星图、魔石更换、技能和分解动作均有原生成功结算。完整新号到大后期、跨账号和长时间断线恢复仍未完成。

## 2026-11-10 旧阶材料回收部署

- 修复材料候选被所有配方一概保护的问题。当前可执行配方与下一解锁等级配方保留，其余满足品质、数量和状态保护条件的材料进入原生回收；缺少权威等级/库存时保持保护。
- `tools/self_test.py`：117 项通过；`tools/validate_bridge.py`：20 项通过；Vite 生产构建通过；候选 EXE 内置自检：117 项通过，报告为 `runtime/candidate-material-salvage-self-test-final.json`。
- 运行中的安装版 worker 原先为修订号 9。更新后的 worker 修订号 10 已由游戏加载器热重载并在实时快照中确认；材料报价绑定堆叠数量和原生报价 ID，执行前复核锁定状态，执行后等待库存记录清零。
- 实机先后完成 9 个与 1 个旧阶材料候选的报价/执行周期；当前仅余材料数据 ID `209303` 和 `209323`，两者均受当前配方保留。当前策略计算不再生成材料分解动作。
- 正式包摘要：`72a8f15da04507cd052a51e87f86a2c7709f2633fc9727c7742690d8c2aaba45`，已同步到 `dist/SHA256.json`。发布前配置备份确认 `auto_start=true`。
- 正常停止并更新助手后，API 恢复为 `running=true`、`connected=true`、`auto_start=true`、16/16 模块开启。游戏 PID `2028` 和启动时间保持不变；未重启游戏。

本次仅证明当前账号当前阶段的材料清理与热加载。新号到大后期、跨账号，以及长时间断线恢复仍未完成验证。

## 2026-11-10 当前阶材料策略与正式部署

- `python -X utf8 tools/self_test.py`：121/121 通过，报告 `runtime/self-test.json`。
- 候选 EXE `--self-test`：121/121 通过，报告 `runtime/candidate-current-tier-material-self-test.json`。
- `python -X utf8 tools/validate_bridge.py`：20/20 通过。
- 策略按角色和配方子类型保护当前可执行阶与下一解锁阶材料；角色等级或配方投影不完整时不生成材料回收动作。回归覆盖材料不足、队伍等级差异与配方字段缺失。
- 正式 EXE 与 `dist/SHA256.json` 哈希一致：`cd63bba4b955945d66674b4b1e3aeb2887d2f57c3d26765537951e1a9ebbaa0c`。部署前正式包、配置、scheduler 和文档备份于 `.private/backups/current-tier-material-deploy-20261110-064153/`。
- 仅重启助手，没有重启游戏。停止前及恢复后 `auto_start=true`；恢复 API `running=true`、`connected=true`、16/16 模块开启。游戏 PID `2028`、启动时间 `2026-11-10 02:28:06` 未变，桥接快照为 `ready`。
- 恢复后新分解动作原生结算成功；最终复核 `pending=null`，主线地图 `500125`、最高通关 `500124`，成功计数 `585`。

当前账号与当前配方阶段已验证；新号到大后期、跨账号和长时间断线恢复仍未通过实机验收。

## 2026-11-10 图鉴材料保护回归与部署

- `python -X utf8 tools/build_release.py --candidate`：源码回归 `125/125`、Godot 桥接边界 `20/20`、Vite 生产构建及候选包构建均通过。
- 候选 EXE 内置自检：`125/125`，报告 `runtime/candidate-collection-safety-self-test.json`。
- 新回归覆盖：跳过锁定材料、当前配方保留材料、缺少配方投影以及背包不存在的过期图鉴候选；同一材料仍只排一个登记请求。
- 将当前权威快照送入策略重算：`recipe_count=104`，图鉴登记候选 `0`，游戏会话 PID `2028`。
- 正式包和 `dist/SHA256.json` 一致：`57a7556165b759385f22165b4c3c9d0971ed8991f9bfb50d4c199ec8023badd3`。部署前备份位于 `.private/backups/collection-item-safety-deploy-20261110/`。
- 只重启了助手，没有重启游戏。恢复后 `running=true`、`connected=true`、`auto_start=true`、16/16 模块开启，`pending=null`；游戏 PID `2028` 与启动时间不变，快照 `phase=ready`。

该验证仍限于当前账号和当前阶段；新号到后期、跨账号和长时间断线恢复未完成。

## 2026-11-10 技能成本双重校验与免重启部署

- 策略调度现在要求技能预览含有效、非空成本，并重新对照当前权威库存计算余额；不能只依赖可能过期的 `can_afford`。
- 桥接在发出技能升级/学习原生请求前，重新读取游戏当前库存，并以刚生成的预览成本再核一次；缺成本、缺余额或余额不足均失败关闭。桥接 revision 从 10 提升到 11。
- `python -X utf8 tools/self_test.py`：127/127；`python -X utf8 tools/validate_bridge.py`：25/25；Vite 生产构建通过。候选包和正式 EXE 的包内自检均为 127/127。
- 正式 EXE 与 `dist/SHA256.json` 一致：`d220079f6c456af9e5d419aeae43db0d363c79656d406c324521b7d050d7ede9`。部署前 EXE、配置、scheduler、worker 和源码备份位于 `.private/backups/skill-cost-release-20261110-072220/`、`%LOCALAPPDATA%/WalletHeroesAssistant/backups/skill-cost-deploy-20261110-072220/`。
- 更新只停止并重启助手，未重启游戏。恢复后 `running=true`、`connected=true`、`auto_start=true`、16/16 模块开启、`pending=null`；游戏 PID `2028` 和启动时间 `2026-11-10 02:28:06` 未变。游戏热加载 worker revision `11` 并保持 `ready`。
- 当前 48 个技能预览中 45 个因技能点余额不足而不可支付，技能队列为 0；部署后没有新的技能升级拒绝。新号到后期、跨账号和长时间断线恢复仍未完成实机验收。


## 2026-11-10 开启状态保存与最少重启正式部署

- 源码回归 `179/179`，报告 `runtime/self-test.json`；候选 EXE 包内自检 `179/179`，报告 `runtime/candidate-connection-recovery-self-test.json`。
- 独立 Godot 桥接边界检查 `58/58`：消耗边界 25 项、连接边界 33 项。Vite 生产构建与 PyInstaller 打包通过。
- 正式 EXE SHA-256 与 `dist/SHA256.json` 一致：`aaa99ea48bbb66123793cfe3697521dc5ce3ab5085e487b4799bf7d77c445cae`。部署备份目录 `.private/backups/connection-release-20261110-083350/`；白名单部署及后续结算证据 `.private/connection-deploy-evidence.json`。
- 停止前、恢复后均为 `auto_start=true`；恢复后 `running=true`、`connected=true`，16/16 模块开启、`pending=null`。退出助手不会清除开启偏好。
- 本次只停止并重启助手，没有重启游戏；部署前后游戏 PID 均为 `2028`，创建时间均为 `1794248886.4586916`，本地启动时间为 `2026-11-10 02:28:06`。loader revision `2` 未修改，worker revision `12` 在原会话热加载，快照 `phase=ready`。
- 后续实机观察到 `stone_merge` 原生成功结算，成功计数 `712 → 713`，跟踪时 `pending=null`、队列为 2 项。
- 回归覆盖普通断线不重启、明确终止错误门槛、最新快照及唯一进程身份复核、正常关闭不强杀、恢复退避跨助手重启保存，以及断线旧库存不计成功和结果未知请求隔离；未为测试主动断网或重启游戏。

当前会话已验证自动化开启状态保留及免重启热加载；跨账号、新号至大后期、长时间断线恢复仍待实机验收。

## 2026-11-10 邮件列表同步退避修复与免重启验证

- 已有源码回归报告 `runtime/self-test.json` 为 `239/239`，候选包内自检报告 `runtime/candidate-mail-refresh-self-test.json` 为 `239/239`；Godot 桥接检查 `58/58`，Vite 与 PyInstaller 构建通过。此次补记录没有变更代码，未重复整套测试。
- 正式 EXE SHA-256：`d661d4e6b5116b8f30e98d794e57c5c428f65152db139fdf8f7d9a733c23a558`；重新读取正式文件计算，与 `dist/SHA256.json` 和部署证据一致。
- 旧邮件长冷却从 `1794353236.860517` 迁移为 `1794272205.6992588`；随后新操作 `7dae3f5cac97490785c03fcee82d4210` 在 `1794272206.717411` 提交，于 `1794272209.2158747` 成功结算。结果文件状态为 `submitted`、`request_ids=[12646]`，原生回执 `ok=true`、`response.ok=true`；调度器记录 `level=success`、`uncertain=false`。
- 最终运行和持久配置均为 `auto_start=true`，`running=true`、`connected=true`、16/16 模块开启，成功计数 `730`；最终采样 `pending_empty=true`、`scheduler_pending_empty=true`。
- 游戏 PID `2028`、创建时间 `1794248886.4586916`（本地 `2026-11-10 02:28:06`）与部署前一致；worker revision `12`、快照 `ready`，未重启游戏。
- 白名单验证证据 `.private/mail-refresh-deploy-evidence.json`；发布备份 `.private/backups/mail-refresh-release-20261110-085443/`；补记录前备份 `.private/backups/mail-refresh-records-20261110-090038/`。

当前会话已通过邮件恢复、开启状态持久化与免重启复核；完整跨账号、新号到大后期和长时间断线恢复仍未完成实机验收。


## 2026-11-10 加载页自动接续与开启状态透传

- 源码回归 `262/262`，报告 `runtime/self-test.json`；候选 EXE 包内自检 `262/262`，报告 `runtime/candidate-loading-start-self-test.json`。
- 独立 Godot 边界检查 `188/188`：消耗 25、连接 33、加载 130，记录 `.private/lab/validation.log`。Vite 生产构建与 PyInstaller 打包通过；本次文档补录未修改代码，未重复整套测试。
- 隔离检查覆盖启动参数按开启偏好透传、已运行游戏不重复启动、加载条件与对象身份检查、断线及暂停禁止请求开始。worker 只设置原生开始请求，由游戏正常完成后续流程。
- 正式 EXE 实际 SHA-256：`25c2a21be516c4e67ee22b679a03eb8de1d98dd63c830aea6279edea6f80f8c6`，与 `dist/SHA256.json`、部署证据一致；发布备份 `.private/backups/loading-release-20261110-094228/`。
- 发布前后游戏 PID `22524`、创建时间 `1794274484.309585`（本地 `2026-11-10 09:34:44`）一致；本次只停止并重新启动助手，未重启游戏。loader revision `2` 未修改，worker revision `13` 已在现有 ready 会话热加载。
- `2026-11-10 09:46:36` 实机复核：配置、control、API 的 `auto_start=true`；`running=true`、`connected=true`、16/16 模块开启；API/scheduler 无 pending、无维护操作。快照 `phase=ready`、年龄约 `0.68` 秒，成功计数 `739 → 742`。
- 正式助手重启后的成功回执如下，仅记录白名单字段；提交状态本身不算成功。
- `stone_merge`：操作 `c5d75a62adc14c2b9eb3593ce1e1525d`，原生回执 `receipt-22524-330.json`，`ok=true`、`response.ok=true`、`uncertain=false`；调度结算时间 `1794275083.5731602` 晚于正式恢复核验 `1794275054.3245037`。
- `stone_equip`：操作 `c2fab4ca73454b0cad2d551a0ca96af4`，原生回执 `receipt-22524-346.json`，`ok=true`、`response.ok=true`、`uncertain=false`；调度结算时间 `1794275101.716411` 晚于正式恢复核验 `1794275054.3245037`。
- `mail_refresh`：操作 `7fdec9ce371244c2b06e4a3d0698971d`，原生回执 `receipt-22524-353.json`，`ok=true`、`response.ok=true`、`uncertain=false`；调度结算时间 `1794275113.8056881` 晚于正式恢复核验 `1794275054.3245037`。

白名单发布及后续成功证据：`.private/loading-deploy-evidence.json`。当前 ready 会话热加载和自动化开启状态持久化通过；真实冷启动加载页、跨账号、新号至大后期及长时间断线恢复仍未完成实机验收。


## 2026-11-10 装备维护事务闭环（revision 14）

- 强化/镶嵌按 prepare、operate、restore 持久化；卸下和穿回使用明确目标状态，权威穿戴结果确认后才推进。暂停、关闭模块、资源不足、报价失效、请求失败或未知结果转为恢复装备，未知消费继续遵守隔离退避。
- 源码与候选包内检查均为 `356/356`，完整场景一致；独立 Godot 边界 `197/197`（消耗 34、连接 33、加载 130）。Vite 与 PyInstaller 构建通过。最终报告为 `runtime/automation-closure-final-self-test.json`、`runtime/automation-closure-packaged-self-test.json`；`runtime/automation-closure-self-test.json` 是 353 项的中途报告。
- revision 14 当时正式包 SHA-256：`4a954e3dba6009f2cffb7f9286e96949d92d34a93dfac4de23e6e23ddf80156a`。部署证据 `runtime/automation-deploy-evidence.json`，备份 `.private/backups/automation-release-20261110-104536/`。只重启助手，游戏 PID `22524`、创建时间 `1794274484.309585` 保持不变。
- 发布流水线必须比较源码与包内完整测试场景，通过后才发布哈希。上述维护异常覆盖来自隔离检查，不能当作真实强化/镶嵌全分支验收。


## 2026-11-10 账号隔离与请求回执归属（revision 16）

- 任务、命令、维护、技能预览与机会快照绑定正整数玩家身份；缺失、格式错误、账号不匹配、已有 pending 或桥接版本不足时拒绝提交。切号隔离旧请求，按账号保存冷却及恢复事务；旧版无身份或损坏的维护记录不接管。
- bridge 执行前再次从即时 gateway 快照核验身份；账号/gateway 变化时释放旧工坊客户端、清除旧报价并刷新导出。新增原生请求记录其发起账号，完成后清理映射，迟到回执不会按回调时的当前账号归档。无法确认归属的回执不写入可结算路径；热加载期间若归属丢失，旧请求保持未知结果保护，不猜测归属或重放消费。
- 回执路径含进程、账号与原生请求号，回执时间不得早于本次提交；同 PID 切号、复用请求号、旧回执、身份暂失、切回维护恢复、损坏状态与重复 dispatch 均有隔离回归。
- 源码回归和候选 EXE 包内检查均为 `381/381`，完整场景一致；正式 EXE 与已检查候选逐字节哈希相同。独立 Godot 检查 `212/212`（消耗 49、连接 33、加载 130），Vite 生产构建与 PyInstaller 打包通过。报告：`runtime/account-isolation-self-test.json`、`runtime/account-isolation-packaged-self-test.json`、`runtime/account-isolation-bridge.log`；构建日志：`runtime/request-receipt-binding-build.log`。
- 正式包、候选包、`dist/SHA256.json` 及部署证据的 SHA-256 一致：`1211676a3d5bdece494bb02bb93055b9e0bb382d5cf8e4fefc1910806f1a6f9c`。发布备份 `.private/backups/account-isolation-release-20261110-113734/`；源码初始备份 `runtime/before-account-isolation-20261110-105344/`。文档与旧报告备份 `.private/backups/automation-records-20261110-114328/`；README 已写明不关闭游戏的助手回滚步骤。
- 部署前后游戏 PID `22524`、创建时间 `1794274484.309585` 一致，当前会话热加载 worker `16`。配置逐字节相同、账号不变；`running=true`、`connected=true`、`auto_start=true`、16/16 模块开启，无挂起请求、无维护事务或调度错误。
- 发布后只读观察中成功计数 `913 → 917`；`mail_refresh`、`loot_claim`、`salvage_quote`、`salvage_execute` 均有账号匹配且 `ok=true`、`response.ok=true` 的原生成功回执。白名单证据：`runtime/account-isolation-deploy-evidence.json`、`runtime/account-isolation-live-evidence.json`，不包含真实账号 ID。

真实切账号及长时间断线未在本轮主动触发。真实冷启动加载页、真实跨账号切换、新号至后期、长时间断线恢复及真实维护状态变化仍待持续验收；当前结果不表示全流程已全面验收。


## 2026-11-10 监控发现原生魔石竞争并修复（revision 17）

首轮监控在 227.97 秒时发现 `stone_merge` 的 `protected_stone`，发布门槛未通过，没有生成分发包。证据 `runtime/monitor-20min-20261110-114855/summary.json`。原生事件显示游戏自身已发起魔石合成，同一组候选先被游戏消费，助手遗漏了魔石原生忙碌状态。

worker 17 将原生合成请求、魔石穿戴请求与手动批量合成纳入 busy；命令执行前再核验。原生忙碌或候选变化时返回明确的未提交结果，助手记为等待刷新，不计成功、不重放旧候选。带原生请求号、未知原因或非魔石操作的“跳过”仍按未知结果隔离。

新增 8 项调度回归与 8 项 Godot 边界检查；源码及候选包内完整场景 389/389、Godot 220/220（57/33/130），Vite 与 PyInstaller 通过。报告 `runtime/stone-concurrency-self-test.json`、`runtime/stone-concurrency-packaged-self-test.json`、`runtime/stone-concurrency-bridge.log`；构建日志 `runtime/stone-concurrency-build.log`。

正式 EXE SHA-256 `98cb5632cc12a086141fddd924d2531c6eaccfd66fd03bcfc573619b960af43d`，与候选及 `dist/SHA256.json` 一致。只更新助手与热加载 worker，游戏 PID 22524、创建时间 1794274484.309585、账号与配置不变；16 项模块及 auto_start 保留。部署证据 `runtime/stone-concurrency-deploy-evidence.json`，备份 `.private/backups/stone-concurrency-release-20261110-115732/`。修复后重新开始完整 20 分钟监控，尚未以本段记录宣称通过。


## 2026-11-10 本机控制接口恢复与诊断

revision 17 更新后一次观测在 17.05 秒时遇到本机 HTTP ConnectionResetError，窗口未通过；游戏快照和后台原生结算持续正常。证据 `runtime/monitor-20min-20261110-115800/summary.json`。GET health、工作台和 state 均无法读取，未以后台继续结算替代接口稳定性验收。

窗口版增加 `server-error.log`，保存 HTTP 线程异常，便于定位无控制台时的接口失败。该诊断改动通过 389 项源码/包内自检、220 项 Godot 边界和前端构建。由于 HTTP 正常停止路径不可用，在确认原生空闲、无 pending、无维护事务且日志已持久化后，仅结束已核验路径的两个助手进程，再启动更新的正式包；没有结束游戏进程，配置逐字节保持。恢复证据 `runtime/control-recovery-evidence.json`，备份 `.private/backups/control-recovery-20261110-120259/`。

当前正式包 SHA-256 `d518f535adcd18a63ecad17167dc2c2e36113068883d84967a40b1def9e26fa5`。控制接口已恢复，但本记录不将未复现的连接重置认定为根因已修复；重新计满 20 分钟稳定窗口后才生成分发包。


## 2026-11-10 连续 20 分钟监控与发布包

2026-11-10 12:03:19 至 2026-11-10 12:23:20（本机时间）连续监控 1200.6 秒，共 211 次采样，未发现调度 warning/error、未知结算、连接中断、快照过期、账号错配或请求超时。成功计数 960 → 985，原生回执核验通过的动作统计：`{"mail_refresh": 4, "loot_claim": 4, "collection_register": 1, "salvage_quote": 6, "salvage_execute": 6, "equipment_equip": 1, "rune_level": 1, "stone_merge": 1, "stone_equip": 1}`。游戏进程、账号、配置和 16 项模块保持不变；窗口终点无 pending 或维护事务。

通过监控后生成 `dist/桌面勇者自动远征-20261110-122337-20分钟验证.zip`，包含同一份已监控 EXE、UTF-8 使用/验证说明、20 分钟监控报告、389 项包内自检报告和 EXE 哈希。暂存 EXE 的隔离自检 389/389，完整场景与源码一致；ZIP 完整性及内置 EXE 哈希均已核验。EXE SHA-256 为 `d518f535adcd18a63ecad17167dc2c2e36113068883d84967a40b1def9e26fa5`；ZIP SHA-256 为 `d13ddafe421c99050871df42aeff4396a4ed84c7dbc3fc1a98203a9deab04bf1`，旁置校验文件为 `dist/桌面勇者自动远征-20261110-122337-20分钟验证.sha256.txt`。未重新启动或替换运行中的助手。

原始采样与发布证据位于 `runtime/monitor-20min-20261110-120318/`，汇总为 `runtime/monitor-20min-release.json`。本次监控只覆盖当前账号和当前会话；真实冷启动、切号、新号至后期、长时间断线和全部维护状态变化仍待验收。


## 2026-11-12 沙盒连接支持与实机部署

原游戏在 21:17 退出后，Steam 于 21:18 在 `xsjsteam` 沙盒中启动新实例。游戏已成功登录并在沙盒目录持续写入快照，沙盒外的旧助手却一直读取本机旧目录，导致页面显示等待连接。新增 `wallet_assistant/sandbox.py`，通过 Sandboxie 的进程和文件根目录 API 绑定单一游戏实例；状态、控制、命令、结果和回执均使用同一通道，配置和调度日志仍保留本机。目录或实例切换时隔离旧请求，快照校验 PID、创建时间和时效；保存沙盒名称供恢复启动沿用。页面显示当前沙盒，多实例不自动接管。

源码及包内隔离自检 410/410（新增 21 项沙盒场景），Godot 边界检查 220/220，前端与单文件构建通过。正式 EXE 与 `桌面勇者自动远征-沙盒版.exe` 内容一致，SHA-256 `ff1e1e7f6edf60de8f8814465ecdafb378033dad50738add1d49171b40f1a7de`。通过旧助手的正常停止入口完成更新，只重新启动助手；游戏 PID 53564、创建时间 1794489537.1052945 保持，config.json 哈希不变。

截至 2026-11-12 21:59:33 UTC+08:00，沙盒连接为 ready、角色等级 29、快照年龄约 0.98 秒；成功计数 3262 → 3273，新增 11 条已核验成功日志。浏览器已刷新并显示“沙盒 · xsjsteam”和“游戏已连接”。证据 `runtime/sandbox-deploy-baseline.json`、`runtime/sandbox-live-evidence.json`、`output/sandbox-connected-20261112.png`，构建日志 `runtime/sandbox-build.log`。备份 `.private/backups/sandbox-support-20261112-214933/`。实机覆盖当前运行会话，沙盒冷启动、长时间断线及其他 Sandboxie 配置尚未实机覆盖；相关恢复路径有隔离测试，本次未宣称完成新的 20 分钟监控。


## 2026-11-13 沙盒内 Steam 更新后连接恢复

根因：沙盒内游戏已更新为 build 26636673，实际进程文件位于 Sandboxie 的 drive/D 副本；常驻助手缓存的是原 D: 安装路径，按完整 exe 路径比较未能找到 PID，连接状态因此一直保持等待。沙盒桥接和游戏登录均正常，不属于服务器连接失败。

增加 `sandbox.virtual_path`，只按该进程所属沙盒根目录的 drive/<盘符> 结构映射回虚拟路径；其他沙盒、不在映射中的路径和普通进程保持原样。不信任命令行来扩大目标匹配。发现游戏与检查现有游戏均使用该映射，继续排除加载辅助进程。新增 8 项场景，验证更新副本、原始路径、普通进程、其他沙盒、发现、实例识别、防止重复启动及当前 IPC 绑定。

源码及包内自检 418/418，Godot 220/220，构建通过。正式 EXE、沙盒版和旁路更新修复 EXE 完全一致，SHA-256 `20947566c8617b36c67fce7f3c96ce2d2342365a42e74d42404acf20b80b5408`。通过旧助手正常停止入口更新，只重启助手；游戏 PID 34904、创建时间与原配置逐字节保持。

截至 2026-11-13 18:40:42 UTC+08:00，页面显示“沙盒 · xsjsteam / 游戏已连接”，角色等级 30，成功计数 4417 → 4425，更新后有 8 条已核验成功日志。证据 `runtime/sandbox-update-path-baseline.json`、`runtime/sandbox-update-path-live-evidence.json`，源码及包内报告 `runtime/sandbox-update-path-source-tests.json`、`runtime/sandbox-update-path-packaged-tests.json`，构建日志 `runtime/sandbox-update-path-build.log`。备份 `.private/backups/sandbox-update-path-20261113-183636/`。验证覆盖当前更新后的真实游戏会话，未宣称完成新的 20 分钟监控、真实更新过程重放或跨机器验证。


## 2026-11-14 接口恢复与沙盒版打包

游戏及桥接继续在线（xsjsteam，角色 32 级），常驻助手的本机 HTTP 接口出现 WinError 10053/10054，正常停止入口无法访问。确认没有待结算、维护任务或原生请求并保存调度记录后，仅重启已核验路径的助手；游戏实例和配置保持。连续 20 次 health/state 请求成功，页面状态接口确认已连接、自动成长开启。本次未确认接口中断根因，未将恢复运行表述为长期稳定性修复。

重新执行当前正式 EXE 包内自检 418/418，通过后生成 `dist/桌面勇者自动远征-沙盒版-20261114.zip`（8019995 字节）。包含 EXE、UTF-8 使用说明、EXE 校验值、验证范围说明和包内自检报告；不包含账号数据、存档或个人配置。ZIP 完整性和内置 EXE 哈希已核验，与当前运行版本一致，EXE SHA-256 `20947566c8617b36c67fce7f3c96ce2d2342365a42e74d42404acf20b80b5408`，ZIP SHA-256 `180da2185a8fa2fd930386f2f649182f12c7fe2ff971eaeafc0d518ef389c23a`。220 项桥接检查沿用同版本构建结果，本次没有源码变更或新的 20 分钟监控。

证据：`runtime/assistant-service-recovery-20261114-baseline.json`、`runtime/assistant-service-recovery-20261114.json`、`runtime/package-20261114-self-test.json`、`runtime/package-20261114-manifest.json`。恢复前备份 `.private/backups/assistant-service-recovery-20261114-174512/`。
