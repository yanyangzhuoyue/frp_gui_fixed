# -*- coding: utf-8 -*-
"""
FRP TOML/INI配置生成GUI V3.7
新增：一键生成启动bat、NSSM安装/卸载Windows服务脚本
兼容：Windows7 / Server2008 32/64
打包：Python3.8.10 32bit + pyinstaller==5.13.2
pyinstaller --onefile --windowed -i app.ico frp_gui_fixed.py
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
import sqlite3
import json
import os
import re

DB_FILE = "frp_config.db"

FRP_VERSION_NOTE = """
==================== FRP Windows版本兼容对照表 ====================
【重要实测提醒】Go语言编译底层限制，旧Windows系统必须打系统补丁，否则程序直接崩溃报错0xc0000005

1. frp v0.52.3
   ⚠️ Windows7 64位旗舰版：**必须安装 Win7 SP1 + KB2533623系统更新包**，否则无法启动；无补丁直接闪退。
   ⚠️ ⚠️若打完全部补丁仍然无法正常启动，请降级使用 frp v0.51.3 或者更早版本。
   ⚠️ Windows7 32位(x86)：官方0.52.3‑386二进制包大量实测启动失败，不推荐使用该版本。
   ⚠️ Windows Server2008 R2：同样必须安装SP1补丁包。
   ✅支持：Win7 SP1(64位)、Server2008 R2 SP1
   ❌不支持：Win7无SP1、Win7‑32位、Server2008(非R2)
   ✅支持旧ini格式，也支持toml

2. frp v0.53.0 ~ v0.58.x
   ❌彻底放弃 Windows7 / Server2008 R2，直接运行崩溃
   ✅最低系统：Windows 8.1 / Server2012 R2 及以上

3. frp v0.59.0 ~ latest最新版
   ✅最低系统：Windows10 / Server2016 及以上
   ✅完全使用toml配置，ini仍然兼容但官方不再推荐

----------------------------------------------------------------------
💡选型建议（按系统）：
 ▶ Windows7 32位(x86)  → 优先使用 frp v0.20.0（最后稳定支持32位Win7，仅基础TCP/UDP/HTTP代理）
 ▶ Windows7 64位旗舰版 → 务必装好 SP1 + KB2533623 更新；v0.52.3启动失败请降级至 v0.51.3
 ▶ Server2008 R2      → 必须SP1补丁，frp v0.52.3；启动异常降级0.51.3；非R2版本不建议跑frp，极易崩溃
 ▶ Server2012 / Win8.1 → 最高可用 v0.58.x
 ▶ Win10 / Server2016及以上 → 直接使用最新frp版本

----------------------------------------------------------------------
补充说明：
• Server2008（非R2）：没有任何官方预编译frp可以稳定运行，不建议部署frp。
• 32位Windows系统，只能下载frp_xxx_windows_386版本；64位系统用amd64。
• 报错0xc0000005：90%是系统缺少SP1/KB2533623补丁，补丁装好依旧报错尝试降级0.51.3。
• 本工具"0.5x旧版"对应v0.52及更早；"0.9x及以上"为新版toml语法。
• Windows服务注册使用NSSM工具，请自行下载nssm.exe放到同目录，管理员运行安装bat。
"""


class FrpDB:
    """SQLite数据库封装"""
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cur = self.conn.cursor()
        self._init_table()

    def _init_table(self):
        self.cur.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            frp_version TEXT DEFAULT "0.9x",
            main_params TEXT,
            proxies_json TEXT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        self.conn.commit()

    def save_config(self, name, mode, frp_ver, main_params, proxies_json):
        self.cur.execute('''
        INSERT INTO configs(name,mode,frp_version,main_params,proxies_json) VALUES (?,?,?,?,?)
        ''', (name, mode, frp_ver, main_params, proxies_json))
        self.conn.commit()
        return self.cur.lastrowid

    def update_config(self, cid, name, mode, frp_ver, main_params, proxies_json):
        self.cur.execute('''
        UPDATE configs SET name=?,mode=?,frp_version=?,main_params=?,proxies_json=? WHERE id=?
        ''', (name, mode, frp_ver, main_params, proxies_json, cid))
        self.conn.commit()

    def list_all(self):
        self.cur.execute("SELECT id,name,mode,frp_version,create_time FROM configs ORDER BY id DESC")
        return self.cur.fetchall()

    def get_one(self, cid):
        self.cur.execute("SELECT * FROM configs WHERE id=?", (cid,))
        return self.cur.fetchone()

    def delete(self, cid):
        self.cur.execute("DELETE FROM configs WHERE id=?", (cid,))
        self.conn.commit()

    def close(self):
        self.conn.close()


class FrpConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FRP配置生成器V3.7｜frps/frpc｜TOML/INI｜SQLite｜BAT/服务脚本")
        self.root.geometry("980x820")
        # =========修复闪烁：初始隐藏窗口=========
        self.root.withdraw()

        try:
            root.option_add("*Font", ("Microsoft YaHei",9))
        except:
            pass

        self.db = FrpDB()
        self.mode_var = tk.StringVar(value="frpc")
        self.frp_ver_var = tk.StringVar(value="0.9x")
        self.proxy_type_var = tk.StringVar(value="tcp")
        self.proxy_list = []
        self.current_db_id = None
        self.edit_proxy_index = None
        self.win_service_name = tk.StringVar(value="FRP_Service")

        self.frpc_fields = [
            ("serverAddr", "服务端IP地址", "0.0.0.0"),
            ("serverPort", "服务端端口", "7000"),
            ("auth.token", "认证Token", ""),
            ("webServer.port", "FRPC管理API端口(0关闭)", "0"),
            ("webServer.user", "API账号", ""),
            ("webServer.password", "API密码", ""),
            ("store.path", "Store持久化JSON路径(留空不启用)", ""),
            ("transport.tls.enable", "启用TLS加密 1开启/0关闭", "0"),
        ]
        self.frps_fields = [
            ("bindPort", "绑定监听端口", "7000"),
            ("auth.token", "认证Token", ""),
            ("vhostHTTPPort", "HTTP虚拟主机端口", "8080"),
            ("vhostHTTPSPort", "HTTPS虚拟主机端口", "8443"),
            ("webServer.port", "FRPS仪表盘端口(0关闭)", "0"),
            ("webServer.user", "仪表盘账号", ""),
            ("webServer.password", "仪表盘密码", ""),
            ("transport.tls.force", "强制TLS连接 1开启/0关闭", "0"),
        ]

        self.entries = {}
        self.input_widgets = []
        self.build_ui()
        self.refresh_db_list()

        self.center_window(self.root)
        self.root.deiconify()

    def show_version_info(self):
        """弹出frp版本兼容说明窗口，弹窗居中"""
        win = tk.Toplevel(self.root)
        win.title("FRP版本与Windows系统兼容说明")
        win.geometry("760x560")
        win.transient(self.root)
        win.grab_set()
        self.center_window(win)

        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Consolas",9))
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert(tk.END, FRP_VERSION_NOTE.strip())
        txt.configure(state="disabled")

        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=4)

    def center_window(self, wnd):
        """通用窗口居中函数，主窗口/子弹窗都调用"""
        wnd.update_idletasks()
        w = wnd.winfo_width()
        h = wnd.winfo_height()
        x = (wnd.winfo_screenwidth() // 2) - (w // 2)
        y = (wnd.winfo_screenheight() // 2) - (h // 2)
        wnd.geometry(f"{w}x{h}+{x}+{y}")

    def build_ui(self):
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=6, pady=6)

        # 左侧数据库面板
        frame_left = ttk.LabelFrame(main_pane, text="📂数据库配置记录")
        main_pane.add(frame_left, weight=1)
        self.tree = ttk.Treeview(frame_left, columns=("name","mode","ver"), show="headings")
        self.tree.heading("name", text="配置名称")
        self.tree.heading("mode", text="类型")
        self.tree.heading("ver", text="FRP版本")
        self.tree.column("name", width=110)
        self.tree.column("mode", width=60)
        self.tree.column("ver", width=70)
        vsb = ttk.Scrollbar(frame_left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="top", fill="both", expand=True, padx=4, pady=4)
        vsb.pack(side="right", fill="y")

        frame_db_btn = ttk.Frame(frame_left)
        frame_db_btn.pack(fill="x", padx=2, pady=3)
        ttk.Button(frame_db_btn, text="新建空白", command=self.new_record).grid(row=0,column=0,sticky="ew")
        ttk.Button(frame_db_btn, text="加载选中", command=self.load_selected).grid(row=0,column=1,sticky="ew")
        ttk.Button(frame_db_btn, text="保存当前", command=self.save_to_db).grid(row=1,column=0,sticky="ew")
        ttk.Button(frame_db_btn, text="删除选中", command=self.del_selected).grid(row=1,column=1,sticky="ew")
        for c in range(2): frame_db_btn.columnconfigure(c, weight=1)

        # 右侧主内容区
        frame_right = ttk.Frame(main_pane)
        main_pane.add(frame_right, weight=3)

        frame_top = ttk.LabelFrame(frame_right, text="运行模式 & FRP版本选择")
        frame_top.pack(fill="x", padx=4, pady=3)

        ttk.Radiobutton(frame_top, text="frpc 客户端", variable=self.mode_var, value="frpc", command=self.switch_mode).grid(row=0,column=0,padx=8)
        ttk.Radiobutton(frame_top, text="frps 服务端", variable=self.mode_var, value="frps", command=self.switch_mode).grid(row=0,column=1,padx=8)

        ttk.Label(frame_top, text="FRP版本:").grid(row=0,column=2,padx=(12,4))
        cbx_ver = ttk.Combobox(frame_top, textvariable=self.frp_ver_var, values=["0.5x旧版","0.9x及以上"], state="readonly", width=12)
        cbx_ver.grid(row=0,column=3)
        cbx_ver.set("0.9x及以上")

        # 【版本说明】按钮
        ttk.Button(frame_top, text="ℹ版本说明", command=self.show_version_info).grid(row=0,column=4,padx=6)
        ttk.Button(frame_top, text="📂导入外部配置文件", command=self.import_external_config).grid(row=0,column=5,padx=6)

        self.frame_param = ttk.LabelFrame(frame_right, text="基础配置参数")
        self.frame_param.pack(fill="x", padx=4, pady=3)
        self.switch_mode()

        # ===代理隧道表单===
        frame_proxy = ttk.LabelFrame(frame_right, text="🔗代理隧道 (仅frpc生效)｜双击表格行编辑")
        frame_proxy.pack(fill="x", padx=4, pady=3)

        pf1 = ttk.Frame(frame_proxy)
        pf1.pack(fill="x", padx=4, pady=2)
        ttk.Label(pf1, text="代理类型:").grid(row=0,column=0)
        cbx = ttk.Combobox(pf1, textvariable=self.proxy_type_var, values=["tcp","udp","http"], state="readonly", width=8)
        cbx.grid(row=0,column=1,padx=4)

        self.proxy_name_var = tk.StringVar()
        self.proxy_local_ip_var = tk.StringVar(value="127.0.0.1")
        self.proxy_local_port_var = tk.StringVar()
        self.proxy_remote_port_var = tk.StringVar()
        self.proxy_custom_domains_var = tk.StringVar()

        ttk.Label(pf1, text="代理名称:").grid(row=0,column=2,padx=4)
        ttk.Entry(pf1, textvariable=self.proxy_name_var, width=14).grid(row=0,column=3)

        pf2 = ttk.Frame(frame_proxy)
        pf2.pack(fill="x", padx=4, pady=2)
        ttk.Label(pf2, text="本地IP:").grid(row=0,column=0)
        ttk.Entry(pf2, textvariable=self.proxy_local_ip_var, width=14).grid(row=0,column=1,padx=2)
        ttk.Label(pf2, text="本地端口:").grid(row=0,column=2)
        ttk.Entry(pf2, textvariable=self.proxy_local_port_var, width=10).grid(row=0,column=3,padx=2)
        ttk.Label(pf2, text="远程端口:").grid(row=0,column=4)
        ttk.Entry(pf2, textvariable=self.proxy_remote_port_var, width=10).grid(row=0,column=5,padx=2)
        ttk.Label(pf2, text="域名(http):").grid(row=0,column=6)
        ttk.Entry(pf2, textvariable=self.proxy_custom_domains_var, width=18).grid(row=0,column=7,padx=2)

        pf3 = ttk.Frame(frame_proxy)
        pf3.pack(fill="x", padx=4, pady=2)
        self.btn_add_proxy = ttk.Button(pf3, text="➕添加代理", command=self.add_proxy_item)
        self.btn_add_proxy.grid(row=0,column=0,padx=4)
        ttk.Button(pf3, text="➖删除选中代理", command=self.del_proxy_item).grid(row=0,column=1,padx=4)
        ttk.Button(pf3, text="清空代理列表", command=self.clear_proxy).grid(row=0,column=2,padx=4)
        ttk.Button(pf3, text="取消编辑", command=self.cancel_edit_proxy).grid(row=0,column=3,padx=4)

        self.proxy_tree = ttk.Treeview(frame_proxy, columns=("type","name","local","remote","domain"), show="headings", height=4)
        self.proxy_tree.heading("type", text="类型")
        self.proxy_tree.heading("name", text="代理名")
        self.proxy_tree.heading("local", text="本地地址")
        self.proxy_tree.heading("remote", text="远程端口")
        self.proxy_tree.heading("domain", text="域名")
        self.proxy_tree.column("type", width=60)
        self.proxy_tree.column("name", width=100)
        self.proxy_tree.column("local", width=110)
        self.proxy_tree.column("remote", width=80)
        self.proxy_tree.column("domain", width=140)
        self.proxy_tree.pack(fill="x", padx=4, pady=3)
        self.proxy_tree.bind("<Double-1>", self.on_proxy_double_click)

        # ==========脚本生成按钮组【新增】==========
        frame_script = ttk.LabelFrame(frame_right, text="📜BAT脚本生成｜NSSM Windows服务")
        frame_script.pack(fill="x", padx=4, pady=3)
        ttk.Label(frame_script, text="Windows服务名:").grid(row=0,column=0,padx=4)
        ttk.Entry(frame_script, textvariable=self.win_service_name, width=22).grid(row=0,column=1,padx=4)

        ttk.Button(frame_script, text="🔹生成启动BAT", command=self.gen_start_bat).grid(row=0,column=2,padx=4)
        ttk.Button(frame_script, text="🔹生成【安装服务BAT】", command=self.gen_install_service_bat).grid(row=0,column=3,padx=4)
        ttk.Button(frame_script, text="🔹生成【卸载服务BAT】", command=self.gen_uninstall_service_bat).grid(row=0,column=4,padx=4)

        #操作按钮
        frame_btn = ttk.Frame(frame_right)
        frame_btn.pack(pady=4)
        ttk.Button(frame_btn, text="🔧生成TOML预览", command=self.gen_config_toml).grid(row=0,column=0,padx=6)
        ttk.Button(frame_btn, text="🔧生成INI预览", command=self.gen_config_ini).grid(row=0,column=1,padx=6)
        ttk.Button(frame_btn, text="💾另存配置文件", command=self.save_file).grid(row=0,column=2,padx=6)
        ttk.Button(frame_btn, text="🧹清空全部", command=self.clear_all).grid(row=0,column=3,padx=6)

        frame_out = ttk.LabelFrame(frame_right, text="配置预览输出")
        frame_out.pack(fill="both", expand=True, padx=4, pady=3)
        self.text_out = scrolledtext.ScrolledText(frame_out, wrap=tk.WORD)
        self.text_out.pack(fill="both", expand=True, padx=4, pady=4)

    # ----------------【新增脚本生成逻辑】----------------
    def gen_start_bat(self):
        """生成普通启动bat脚本"""
        mode = self.mode_var.get()
        ver_sel = self.frp_ver_var.get()
        ext = "ini" if ver_sel == "0.5x旧版" else "toml"
        bat_content = f'''@echo off
chcp 65001
echo ======================================
echo  {mode}.bat FRP启动脚本
echo  请把 {mode}.exe 和 {mode}.{ext} 放在同一目录
echo ======================================
pause
{mode}.exe -c {mode}.{ext}
pause
'''
        fp = filedialog.asksaveasfilename(defaultextension=".bat", initialfile=f"{mode}_启动.bat", filetypes=[("BAT脚本","*.bat"),("所有文件","*.*")])
        if fp:
            with open(fp,"w",encoding="gbk") as f:
                f.write(bat_content)
            messagebox.showinfo("完成",f"已保存 {os.path.basename(fp)}\n注意：frp程序、配置文件、bat放在同一个文件夹。")

    def gen_install_service_bat(self):
        """NSSM安装windows服务bat"""
        mode = self.mode_var.get()
        ver_sel = self.frp_ver_var.get()
        ext = "ini" if ver_sel == "0.5x旧版" else "toml"
        svc_name = self.win_service_name.get().strip()
        if not svc_name:
            messagebox.showwarning("输入错误","请填写Windows服务名称")
            return
        bat_content = f'''@echo off
chcp 65001
echo =====================================================
echo  NSSM安装Windows服务脚本 {svc_name}
echo 【重要】1.必须右键【以管理员身份运行】此bat
echo         2.把 nssm.exe, {mode}.exe, {mode}.{ext} 全部放在同一个目录
echo         3.32位系统使用win32/nssm.exe；64位使用win64/nssm.exe
echo =====================================================
pause
nssm install {svc_name} "%~dp0{mode}.exe" "-c %~dp0{mode}.{ext}"
nssm set {svc_name} DisplayName "{svc_name}"
nssm set {svc_name} Description "FRP {mode} 内网穿透服务"
nssm set {svc_name} Start SERVICE_AUTO_START
nssm start {svc_name}
echo.
echo 服务安装完成！如报错，请检查nssm.exe是否存在，管理员权限。
pause
'''
        fp = filedialog.asksaveasfilename(defaultextension=".bat", initialfile=f"{svc_name}_安装服务.bat", filetypes=[("BAT脚本","*.bat")])
        if fp:
            with open(fp,"w",encoding="gbk") as f:
                f.write(bat_content)
            messagebox.showinfo("生成完成",f"已保存 {os.path.basename(fp)}\n⚠️必须管理员运行；需要nssm.exe在同目录！")

    def gen_uninstall_service_bat(self):
        """NSSM卸载服务bat"""
        svc_name = self.win_service_name.get().strip()
        if not svc_name:
            messagebox.showwarning("输入错误","请填写Windows服务名称")
            return
        bat_content = f'''@echo off
chcp 65001
echo =====================================================
echo 卸载Windows服务 {svc_name}
echo ⚠️右键【以管理员身份运行】
echo =====================================================
pause
nssm stop {svc_name}
nssm remove {svc_name} confirm
echo 服务已卸载
pause
'''
        fp = filedialog.asksaveasfilename(defaultextension=".bat", initialfile=f"{svc_name}_卸载服务.bat", filetypes=[("BAT脚本","*.bat")])
        if fp:
            with open(fp,"w",encoding="gbk") as f:
                f.write(bat_content)
            messagebox.showinfo("生成完成",f"已保存 {os.path.basename(fp)}\n⚠️管理员运行，需要nssm.exe同目录。")

    # ----------------代理编辑逻辑----------------
    def on_proxy_double_click(self, event):
        sel = self.proxy_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.edit_proxy_index = idx
        item = self.proxy_list[idx]
        self.proxy_type_var.set(item["type"])
        self.proxy_name_var.set(item["name"])
        self.proxy_local_ip_var.set(item["local_ip"])
        self.proxy_local_port_var.set(item["local_port"])
        self.proxy_remote_port_var.set(item["remote_port"])
        self.proxy_custom_domains_var.set(item["custom_domains"])
        self.btn_add_proxy.config(text="✅更新代理")

    def cancel_edit_proxy(self):
        self.edit_proxy_index = None
        self.btn_add_proxy.config(text="➕添加代理")
        self.proxy_name_var.set("")
        self.proxy_local_port_var.set("")
        self.proxy_remote_port_var.set("")
        self.proxy_custom_domains_var.set("")

    def add_proxy_item(self):
        ptype = self.proxy_type_var.get()
        pname = self.proxy_name_var.get().strip()
        lip = self.proxy_local_ip_var.get().strip()
        lport = self.proxy_local_port_var.get().strip()
        rport = self.proxy_remote_port_var.get().strip()
        domains = self.proxy_custom_domains_var.get().strip()
        if not all([pname,lip,lport]):
            messagebox.showwarning("参数不全","代理名称、本地IP、本地端口不能为空")
            return
        item = {
            "type":ptype,
            "name":pname,
            "local_ip":lip,
            "local_port":lport,
            "remote_port":rport,
            "custom_domains":domains
        }
        if self.edit_proxy_index is not None:
            self.proxy_list[self.edit_proxy_index] = item
            self.cancel_edit_proxy()
        else:
            self.proxy_list.append(item)
        self.sync_proxy_tree()

    def del_proxy_item(self):
        sel = self.proxy_tree.selection()
        if not sel: return
        idx = int(sel[0])
        del self.proxy_list[idx]
        if self.edit_proxy_index == idx:
            self.cancel_edit_proxy()
        self.sync_proxy_tree()

    def clear_proxy(self):
        self.proxy_list.clear()
        self.cancel_edit_proxy()
        self.sync_proxy_tree()

    def sync_proxy_tree(self):
        for i in self.proxy_tree.get_children():
            self.proxy_tree.delete(i)
        for idx,p in enumerate(self.proxy_list):
            self.proxy_tree.insert("", tk.END, iid=str(idx), values=(
                p["type"],p["name"],f'{p["local_ip"]}:{p["local_port"]}',
                p["remote_port"], p["custom_domains"]
            ))

    # ============导入外部ini/toml配置============
    def import_external_config(self):
        fp = filedialog.askopenfilename(filetypes=[("FRP配置文件","*.ini;*.toml"),("所有文件","*.*")])
        if not fp:
            return
        try:
            with open(fp,"r",encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            messagebox.showerror("读取文件失败",str(e))
            return
        self.clear_all()
        lines = [x.strip() for x in raw.splitlines()]
        section_data = {}
        current_sec = None
        proxy_list_temp = []
        common_data = {}

        for line in lines:
            if not line or line.startswith("#"):
                continue
            sec_match = re.match(r'^\[(.*)\]$',line)
            if sec_match:
                current_sec = sec_match.group(1).strip()
                continue
            kv = re.split(r"\s*=\s*", line, maxsplit=1)
            if len(kv)!=2:
                continue
            k,v = kv
            k = k.lower()
            v = v.strip().strip('"').strip("'")
            if current_sec == "common":
                common_data[k] = v
            elif current_sec and current_sec != "common":
                proxy_list_temp.append({"sec_name":current_sec,"k":k,"v":v})

        is_frps = False
        if "bind_port" in common_data:
            is_frps = True
        self.mode_var.set("frps" if is_frps else "frpc")
        self.switch_mode()

        field_map_frpc = {
            "server_addr":"serverAddr",
            "server_port":"serverPort",
            "token":"auth.token",
            "admin_port":"webServer.port",
            "tls_enable":"transport.tls.enable",
            "store_file":"store.path"
        }
        field_map_frps = {
            "bind_port":"bindPort",
            "token":"auth.token",
            "vhost_http_port":"vhostHTTPPort",
            "vhost_https_port":"vhostHTTPSPort",
            "dashboard_port":"webServer.port",
            "tls_force":"transport.tls.force"
        }
        fm = field_map_frps if is_frps else field_map_frpc
        for orig_k,gui_key in fm.items():
            if orig_k in common_data and gui_key in self.entries:
                val = common_data[orig_k]
                self.entries[gui_key].delete(0,tk.END)
                self.entries[gui_key].insert(0,val)

        if not is_frps:
            proxy_dict = {}
            for item in proxy_list_temp:
                sname = item["sec_name"]
                if sname not in proxy_dict:
                    proxy_dict[sname] = {}
                proxy_dict[sname][item["k"]] = item["v"]
            for p_name,pkv in proxy_dict.items():
                pt = pkv.get("type","tcp")
                lip = pkv.get("local_ip","127.0.0.1")
                lp = pkv.get("local_port","")
                rp = pkv.get("remote_port","")
                dom = pkv.get("custom_domains","")
                self.proxy_list.append({
                    "type":pt,
                    "name":p_name,
                    "local_ip":lip,
                    "local_port":lp,
                    "remote_port":rp,
                    "custom_domains":dom
                })
        self.sync_proxy_tree()
        self.gen_config_toml()
        messagebox.showinfo("导入完成",f"已导入 {os.path.basename(fp)}\n请核对参数，部分高级参数不会自动解析。")

    # ----------------数据库----------------
    def refresh_db_list(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        rows = self.db.list_all()
        for rid,name,mode,frpver,_ in rows:
            self.tree.insert("", tk.END, iid=str(rid), values=(name,mode,frpver))

    def new_record(self):
        self.clear_all()
        self.current_db_id = None
        self.frp_ver_var.set("0.9x及以上")
        self.win_service_name.set("FRP_Service")
        messagebox.showinfo("提示","已新建空白配置，填写后点【保存当前】存入数据库")

    def save_to_db(self):
        old_name = ""
        old_ver = "0.9x"
        if self.current_db_id is not None:
            row = self.db.get_one(self.current_db_id)
            if row:
                old_name = row[1]
                old_ver = row[3]
        name = simpledialog.askstring("保存配置","输入这套配置的名称：",initialvalue=old_name)
        if not name or not name.strip():
            return
        name = name.strip()
        mode = self.mode_var.get()
        frp_ver = self.frp_ver_var.get()
        main_params = {}
        for k,w in self.entries.items():
            main_params[k] = w.get().strip()
        proxies_json = json.dumps(self.proxy_list, ensure_ascii=False)
        if self.current_db_id:
            self.db.update_config(self.current_db_id, name, mode, frp_ver, json.dumps(main_params), proxies_json)
            messagebox.showinfo("成功",f"✅已覆盖更新ID:{self.current_db_id}数据库记录")
        else:
            self.current_db_id = self.db.save_config(name, mode, frp_ver, json.dumps(main_params), proxies_json)
            messagebox.showinfo("成功","✅新建配置存入SQLite数据库")
        self.refresh_db_list()

    def load_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示","请在左侧选中一条记录")
            return
        cid = int(sel[0])
        row = self.db.get_one(cid)
        if not row: return
        self.current_db_id = cid
        _,name,mode,frp_ver,main_params_str,proxies_str,_ = row
        main_params = json.loads(main_params_str)
        proxies = json.loads(proxies_str)

        self.mode_var.set(mode)
        self.frp_ver_var.set(frp_ver)
        self.switch_mode()
        for k in self.entries:
            val = main_params.get(k,"")
            self.entries[k].delete(0,tk.END)
            self.entries[k].insert(0,val)

        self.proxy_list = proxies
        self.cancel_edit_proxy()
        self.sync_proxy_tree()
        messagebox.showinfo("加载完成",f"已加载配置：{name}\n⚠️现在保存会覆盖这条记录！")

    def del_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("确认删除","确定删除该数据库记录？不可恢复！"):
            return
        cid = int(sel[0])
        self.db.delete(cid)
        if self.current_db_id == cid:
            self.current_db_id = None
        self.refresh_db_list()

    # ----------------基础UI切换----------------
    def clear_param_frame(self):
        for w in self.input_widgets:
            w.destroy()
        self.input_widgets.clear()
        self.entries.clear()

    def switch_mode(self):
        self.clear_param_frame()
        mode = self.mode_var.get()
        fields = self.frpc_fields if mode == "frpc" else self.frps_fields
        for idx,(key,label,default_val) in enumerate(fields):
            lbl = ttk.Label(self.frame_param, text=f"{label}:")
            lbl.grid(row=idx, column=0, sticky="w", padx=6, pady=2)
            ent = ttk.Entry(self.frame_param, width=54)
            ent.insert(0, default_val)
            ent.grid(row=idx, column=1, padx=6, pady=2)
            self.entries[key] = ent
            self.input_widgets.append(lbl)
            self.input_widgets.append(ent)

    # ----------------生成TOML，区分0.5x旧版/0.9x新版字段名差异----------------
    def gen_config_toml(self):
        mode = self.mode_var.get()
        ver_sel = self.frp_ver_var.get()
        is_old_ver = (ver_sel == "0.5x旧版")

        lines = []
        if mode == "frpc":
            lines.append(f"# frpc.toml  {ver_sel}")
        else:
            lines.append(f"# frps.toml  {ver_sel}")
        lines.append("")

        old_key_map = {
            "serverAddr":"server_addr",
            "serverPort":"server_port",
            "bindPort":"bind_port",
            "auth.token":"token",
            "webServer.port":"web_port",
            "webServer.user":"web_user",
            "webServer.password":"web_password",
            "vhostHTTPPort":"vhost_http_port",
            "vhostHTTPSPort":"vhost_https_port",
            "transport.tls.enable":"tls_enable",
            "transport.tls.force":"tls_force",
            "store.path":"store_file"
        }

        for k,widget in self.entries.items():
            val = widget.get().strip()
            if val == "":
                continue
            use_key = old_key_map.get(k,k) if is_old_ver else k
            if val in ("1","0") and ("enable" in k or "force" in k):
                real_val = "true" if val == "1" else "false"
                lines.append(f"{use_key} = {real_val}")
            elif val.isdigit():
                lines.append(f"{use_key} = {val}")
            else:
                lines.append(f'{use_key} = "{val}"')
        lines.append("")

        if mode == "frpc":
            for p in self.proxy_list:
                lines.append("[[proxies]]")
                lines.append(f'name = "{p["name"]}"')
                lines.append(f'type = "{p["type"]}"')
                lines.append(f'localIP = "{p["local_ip"]}"')
                lines.append(f'localPort = {p["local_port"]}')
                if p["remote_port"] and p["remote_port"].isdigit():
                    lines.append(f'remotePort = {p["remote_port"]}')
                if p["custom_domains"]:
                    lines.append(f'customDomains = ["{p["custom_domains"]}"]')
                lines.append("")

        out_text = "\n".join(lines)
        self.text_out.delete(1.0, tk.END)
        self.text_out.insert(tk.END, out_text)

    # ----------------生成INI（旧版frp格式）----------------
    def gen_config_ini(self):
        mode = self.mode_var.get()
        lines = []
        if mode == "frpc":
            lines.append("[common]")
            lines.append("# frpc.ini 旧版ini配置")
            svr_addr = self.entries["serverAddr"].get().strip()
            svr_port = self.entries["serverPort"].get().strip()
            token = self.entries["auth.token"].get().strip()
            api_port = self.entries["webServer.port"].get().strip()
            tls_en = self.entries["transport.tls.enable"].get().strip()

            if svr_addr: lines.append(f"server_addr = {svr_addr}")
            if svr_port: lines.append(f"server_port = {svr_port}")
            if token: lines.append(f"token = {token}")
            if api_port and api_port != "0": lines.append(f"admin_port = {api_port}")
            if tls_en == "1": lines.append("tls_enable = true")
            lines.append("")

            for p in self.proxy_list:
                lines.append(f"[{p['name']}]")
                lines.append(f"type = {p['type']}")
                lines.append(f"local_ip = {p['local_ip']}")
                lines.append(f"local_port = {p['local_port']}")
                if p["remote_port"] and p["remote_port"].isdigit():
                    lines.append(f"remote_port = {p['remote_port']}")
                if p["custom_domains"]:
                    lines.append(f"custom_domains = {p['custom_domains']}")
                lines.append("")
        else:
            lines.append("[common]")
            lines.append("# frps.ini 旧版ini配置")
            bind_port = self.entries["bindPort"].get().strip()
            token = self.entries["auth.token"].get().strip()
            http_port = self.entries["vhostHTTPPort"].get().strip()
            https_port = self.entries["vhostHTTPSPort"].get().strip()
            dash_port = self.entries["webServer.port"].get().strip()
            tls_force = self.entries["transport.tls.force"].get().strip()

            if bind_port: lines.append(f"bind_port = {bind_port}")
            if token: lines.append(f"token = {token}")
            if http_port: lines.append(f"vhost_http_port = {http_port}")
            if https_port: lines.append(f"vhost_https_port = {https_port}")
            if dash_port and dash_port != "0": lines.append(f"dashboard_port = {dash_port}")
            if tls_force == "1": lines.append("tls_force = true")

        out_text = "\n".join(lines)
        self.text_out.delete(1.0, tk.END)
        self.text_out.insert(tk.END, out_text)

    def save_file(self):
        content = self.text_out.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("提示","先生成TOML或者INI预览")
            return
        mode = self.mode_var.get()
        fp = filedialog.asksaveasfilename(
            filetypes=[
                ("TOML配置文件","*.toml"),
                ("INI配置文件","*.ini"),
                ("所有文件","*.*")
            ],
            initialfile=f"{mode}.toml"
        )
        if fp:
            try:
                with open(fp,"w",encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("成功",f"已保存 {fp}")
            except Exception as e:
                messagebox.showerror("保存失败",str(e))

    def clear_all(self):
        self.text_out.delete(1.0, tk.END)
        self.current_db_id = None
        self.frp_ver_var.set("0.9x及以上")
        self.win_service_name.set("FRP_Service")
        self.switch_mode()
        self.clear_proxy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FrpConfigGUI(root)
    root.mainloop()
    app.db.close()