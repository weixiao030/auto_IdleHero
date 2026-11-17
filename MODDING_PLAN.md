# Desktop Wallet Heroes 实现路线

保留原游戏程序与 Steam 所有权流程，用外部 Godot autoload 运行自有控制桥接。所有成长通过原客户端已有入口和服务器回执完成。安装前备份 override.cfg 和游戏用户目录，配置原子写入，提供移除入口。

## 成长闭环覆盖表

| 系统 | 已确认入口或类 | 所需闭环 |
| --- | --- | --- |
| 首次初始化/角色 | AccountBootstrapCoordinator, HeroProgressionFacade | 自动选角、招聘、解锁阵位、配置阵容 |
| 挂机/主线/副本 | BasicCombatSim, AutoTransitionCoordinator, portal map | 推图、失败回刷、成长后重试、奖励结算 |
| 魔石 | ProgressionActions | 择优穿戴、合成、按槽位与职业兼容筛选 |
| 装备 | ProgressionActions, equipment preview | 鉴定、择优、强化、镶嵌、仓库管理 |
| 技能 | SkillProgressionClient | 解锁、升级、自动配置与职业匹配 |
| 符文 | rune page controller | 成本检查、路径配置、持续加点 |
| 魔方/星座 | cube progression, constellation blessings | 解锁、升级、资源预算联动 |
| 工坊 | craft/enhancement/socket/disassembly clients | 配方、材料获取、制造、强化、镶嵌、分解 |
| 领取/图鉴 | pending loot, mail, item collection | 自动领取、登记与剩余资源循环 |
| 连接与启动 | runtime session coordinator | 单实例、掉线恢复、异步结算跟踪 |

当前为基于实际代码的待实现清单，各条都需要独立实机证据，不能将入口存在当作功能完成。
