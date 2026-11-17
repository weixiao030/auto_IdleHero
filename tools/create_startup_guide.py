"""Build the user startup guide using the bundled document runtime."""
from pathlib import Path
import os
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

ROOT=Path(__file__).resolve().parent.parent
doc=Document()
section=doc.sections[0]
section.page_height=Cm(27.94); section.page_width=Cm(21.59)
section.top_margin=Cm(1.9); section.bottom_margin=Cm(1.8)
section.left_margin=section.right_margin=Cm(2.1)
for name in ('Normal','Title','Subtitle','Heading 1','Heading 2','List Number','List Bullet'):
    style=doc.styles[name]; style.font.name='Microsoft YaHei'
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'Microsoft YaHei')
    style.font.color.rgb=RGBColor(0,0,0)
    style.font.size=Pt(11 if name not in ('Title','Heading 1','Heading 2') else {'Title':23,'Heading 1':17,'Heading 2':12}[name])
    style.paragraph_format.space_after=Pt(5)
    style.paragraph_format.line_spacing=1.12
    snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0')
    style.element.get_or_add_pPr().append(snap)
doc.styles['Heading 1'].paragraph_format.space_before=Pt(8)
doc.styles['Heading 2'].paragraph_format.space_before=Pt(10)
doc.core_properties.title='桌面勇者自动远征启动教程'
doc.core_properties.author=''
doc.core_properties.subject='本机与 Sandboxie 多实例启动和日常维护'
for border in list(doc.styles.element.iter(qn('w:pBdr'))): border.getparent().remove(border)
doc.styles['Subtitle'].font.italic=False

def p(text, style=None): return doc.add_paragraph(text,style)
def h(text): doc.add_heading(text,2)
def step(text): p(text,'List Number')
def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for cell,text,width in zip(t.rows[0].cells,headers,widths):cell.text=text;cell.width=Cm(width)
    for values in rows:
        cells=t.add_row().cells
        for cell,text,width in zip(cells,values,widths):cell.text=text;cell.width=Cm(width)
    for ri,row in enumerate(t.rows):
        for cell in row.cells:
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr()
            borders=OxmlElement('w:tcBorders')
            for edge in ('top','left','bottom','right'):
                el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'5');el.set(qn('w:color'),'D9D9D9');borders.append(el)
            tcpr.append(borders)
            margins=OxmlElement('w:tcMar')
            for edge in ('top','bottom','left','right'):
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'105');el.set(qn('w:type'),'dxa');margins.append(el)
            tcpr.append(margins)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E4EAF0' if ri==0 else 'FFFFFF');tcpr.append(shade)
            for para in cell.paragraphs:
                para.paragraph_format.space_after=Pt(2);para.paragraph_format.line_spacing=1.12
                for run in para.runs:run.font.size=Pt(10);run.bold=ri==0
        if ri==0:
            repeat=OxmlElement('w:tblHeader');row._tr.get_or_add_trPr().append(repeat)
    spacer=p('');spacer.paragraph_format.space_after=Pt(0);spacer.paragraph_format.line_spacing=Pt(3)
    return t

p('桌面勇者自动远征启动教程','Title')
p('0.4.0 多实例版  2026年11月16日','Subtitle')
p('本教程说明本机和 Sandboxie 沙盒内的游戏如何接入同一个网页工作台。每个游戏实例有独立的自动化开关、配置、请求和日志，可同时执行自动化。自动重连默认关闭，助手不会因此自动启动或重启游戏。')
h('本机启动')
step('把压缩包完整解压到固定文件夹。使用“桌面勇者自动远征.exe”；沙盒版 EXE 功能相同，任选一个启动。')
step('先打开 Steam 并登录，再启动 Desktop Wallet Heroes，完成游戏登录和加载。')
step('双击助手 EXE。助手定位游戏并安装或更新自有桥接，自动打开网页；已有桥接支持热更新。首次安装时若游戏没有载入桥接，等待游戏结算后手动正常退出并重新打开游戏。')
step('若浏览器没有打开，手动输入下方地址。助手必须保持运行，浏览器页面可以关闭后再打开。')
p('网页工作台：http://127.0.0.1:17470/')
step('查看顶部“实例连接管理”。出现“已连接当前游戏实例”，且 PID 与目标环境对应后，再检查自动化开关。')
step('“开始自动成长”只开启当前选中实例。“暂停自动成长”保留该实例的模块和参数，已提交请求继续等待结算。')
h('先区分两个开关')
p('“启动后自动成长”决定接入游戏后是否执行已开启的功能，沿用上次保存状态。“自动重连”决定是否由助手恢复退出或明确可恢复的游戏实例，默认关闭。网页自动刷新状态与自动重连是两回事。')
h('正常退出助手')
p('关闭网页不会退出助手。需要完全退出时，在 EXE 所在目录执行：')
p('.\桌面勇者自动远征.exe --stop')
p('该命令停止所有实例的助手调度，保留游戏和已保存的开关设置。')

doc.add_page_break();doc.add_heading('沙盒启动与多实例运行',1)
p('在沙盒外运行一个助手即可发现本机及多个沙盒中的游戏。')
step('在 Sandboxie Plus 中准备各沙盒，在第一个沙盒内启动对应的 Steam 和游戏，完成登录与加载。不同会话使用各自的登录环境。')
step('在其他沙盒重复上述步骤，无需关闭已有游戏。同一沙盒内不同 PID 也能分别接入；能否多开仍取决于游戏和 Steam 自身限制。')
step('在沙盒外启动一次助手，打开网页，点击“重新检测本机与沙盒”。后台约每 5 秒重新发现进程。')
step('每个实例会显示独立卡片：本机或沙盒名、PID、连接状态与自动化状态。选择一张卡片查看并修改该实例。')
step('逐个实例确认参数与模块，然后分别开启自动成长。切换查看实例不会暂停其他实例，多个已开启的实例会各自执行自动化。')
h('避免操作错实例')
p('参数、暂停、巡检和快捷键都作用于当前选中实例。切换后先核对沙盒名和 PID；下方角色、背包、日志和队列随之切换。')
table(['页面提示','含义'],[
('已连接当前游戏实例','桥接已输出当前进程的有效游戏数据。'),
('当前游戏尚未连接','游戏未运行、尚在加载登录、桥接尚未生效或数据过期。'),
('自动化暂停','已保存暂停状态，不再提交新的成长操作。'),
('等待原生结算','已发出请求，正在核验游戏回执和实际状态。'),
('自动重连已关闭','不会自动启动或重启；手动打开游戏后仍会发现并接入。')],[5.3,11.3])
h('游戏退出之后')
p('手动在原环境启动游戏后点击重新检测。已发现的离线环境也可使用卡片下的“手动启动此环境的游戏”，先核对环境再点击。')

doc.add_page_break();doc.add_heading('功能设置与降低占用',1)
p('打开“成长策略”，每个功能的参数位于对应开关下方。修改数字后失焦或按回车保存；页面会显示保存结果。各实例分别保存设置，修改一个不会覆盖另一个。')
table(['功能组','包含的功能'],[
('探索与领取','主线推进、自动宝箱、邮件奖励、副本挑战、战斗补给。'),
('装备与魔石','自动鉴定、战力换装、石头优化、换装后分解、装备强化、宝石镶嵌。'),
('角色与成长','角色与阵容、技能养成、星座加点、魔方制造、永久图鉴。'),
('性能与显示','性能模式、目标帧率、极简特效。')],[4.2,12.4])
h('每个实例的首次检查')
step('检查“基础参数”的金币保留数量、金币保留比例与成长操作间隔。新实例继承本机模板，之后独立保存。')
step('检查“换装后分解”的品质范围。默认允许普通、高级和稀有品质；Steam 可交易、已装备、锁定等保护规则持续生效。')
step('检查强化开关；“允许有损坏概率的强化”默认关闭。未解锁或材料不足时，功能会等待条件满足。')
step('查看“运行记录”。“已提交”表示请求已发出，只有回执和状态核验通过才计入“已结算”。')
h('降低占用')
p('可对每个游戏开启“性能模式”，并把目标帧率设为 10 至 30 FPS。关闭性能模式会恢复原来的帧率上限。“极简特效”隐藏特效图层，关闭后恢复显示；这些选项不代替游戏服务器结算。')
p('网页前台约 3 秒、后台约 15 秒刷新。游戏数量增加时仍会增加 CPU 和内存使用；可按需提高成长操作间隔。')
h('快捷键')
p('快捷键被占用时使用网页开关。立即巡检可能消耗游戏资源，仍遵守当前开关、保护规则与请求退避。')
p('F8：自动成长总开关；F9：换装后分解；F10：战力换装。均只控制当前选中实例。')

doc.add_page_break();doc.add_heading('连接排查与后续更新',1)
h('网页打不开')
p('确认助手仍在运行，地址为 http://127.0.0.1:17470/。提示“助手网页服务未响应”时，重新打开助手和网页。重复启动助手会打开同一工作台。')
h('网页能打开但游戏未连接')
step('核对实例卡片的沙盒名和 PID。确认该环境内的游戏已完成登录，不停留在加载页。')
step('点击重新检测并等待一轮更新。实例显示但数据过期时，查看游戏是否卡住、暂停或正在切换场景。')
step('首次安装后仍无数据时，等待游戏当前操作结束，手动正常退出目标游戏并在同一环境重新打开。其他实例可以保持运行。')
step('沙盒中没有发现游戏时，检查 Sandboxie 服务和对应沙盒是否正常。新版不要求关闭沙盒隔离，也不自动修改沙盒安全策略。')
h('功能一直等待')
p('先确认当前实例已连接、自动化总开关与相应模块均开启。再查看运行记录和模块的等待原因：未解锁、材料不足、容量不足、请求正在结算、候选过期等情况均会等待。结果未知的消费请求不会自动重放。')
h('配置与日志保存位置')
p(r'数据根目录：%LOCALAPPDATA%\WalletHeroesAssistant\。每实例的配置和日志位于 instances 子目录；网页“基础参数”中的“打开配置文件”定位当前实例，保存后约每 5 秒重载。')
p('无效 JSON 保留上次有效配置。有待结算操作时不要删除调度或通信文件。分发包不含个人配置、账号日志和存档。')
h('更新与回退')
step('暂停各实例，等原生结算和装备维护完成，执行 --stop，替换 EXE 后重新打开。')
step('保留整个数据根目录。游戏更新后先核对连接和兼容性，再恢复自动化。')
step('回退前备份当前数据，停止助手后换回旧 EXE。旧版仅支持单实例，先正常退出其余游戏，并保留新版数据备份。')
p('本版检查范围和未现场覆盖的功能条件见随包“验证说明”。需要进一步逆向游戏时使用 IDA。')

output=ROOT/'dist/桌面勇者自动远征启动教程.docx'
temporary=output.with_name(output.stem+'.tmp.docx')
doc.save(temporary)
os.replace(temporary,output)
print(output)
