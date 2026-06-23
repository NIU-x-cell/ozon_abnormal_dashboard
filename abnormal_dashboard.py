import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, true

# ===================== MySQL数据库配置 =====================


# 从Streamlit后台密钥读取数据库信息
MYSQL_USER = st.secrets["MYSQL_USER"]
MYSQL_PWD = st.secrets["MYSQL_PWD"]
MYSQL_HOST = st.secrets["MYSQL_HOST"]
MYSQL_PORT = st.secrets["MYSQL_PORT"]
DB_NAME = st.secrets["MYSQL_DB"]
# 临时测试，成功会打印账号，报错就是密钥读取失败
st.write(MYSQL_USER)

engine = create_engine(f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PWD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}")
# ==========================================================


# 页面全局基础配置
st.set_page_config(page_title="Ozon采购链接异常分析看板", layout="wide")
# 读取完整业务数据表
sql_query = "SELECT * FROM `采购链接异常处理表`;"
df_all = pd.read_sql(sql_query, con=engine)
df_all["创建时间"] = pd.to_datetime(df_all["创建时间"])

# 侧边栏日期筛选
st.sidebar.header("自定义筛选日期范围")
min_data_dt = df_all["创建时间"].min()
max_data_dt = df_all["创建时间"].max()
start_dt, end_dt = st.sidebar.date_input(
    "选择查询起止日期",
    value=[max_data_dt - pd.Timedelta(days=6), max_data_dt], # 默认近7天（一周）
    min_value=min_data_dt,
    max_value=max_data_dt
)
start_dt = pd.to_datetime(start_dt)
end_dt = pd.to_datetime(end_dt)

# 1、当前筛选区间数据（图表、明细、透视表全部使用这套数据）
df_curr_range = df_all[(df_all["创建时间"] >= start_dt) & (df_all["创建时间"] <= end_dt)]

# 2、自动计算上一个同等长度区间（仅用于KPI环比对比）
range_days = (end_dt - start_dt).days + 1
last_end_dt = start_dt - pd.Timedelta(days=1)
last_start_dt = last_end_dt - pd.Timedelta(days=range_days - 1)
df_last_range = df_all[(df_all["创建时间"] >= last_start_dt) & (df_all["创建时间"] <= last_end_dt)]

# 区间文字展示
curr_label = f"{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}"
last_label = f"{last_start_dt.strftime('%Y-%m-%d')} ~ {last_end_dt.strftime('%Y-%m-%d')}"

# 通用环比计算函数
def calc_ratio(curr_num, last_num):
    if last_num == 0:
        return "无上期数据"
    ratio = (curr_num - last_num) / last_num
    return f"{ratio:.2%}"

# ========== 负责人分组专用完工时效均值函数 ==========
# 统一时效计算：只统计已完工工单（处理情况≠待处理）
def get_avg_handle(df_sub):
    # 筛选出所有不是待处理的完工工单
    df_solved = df_sub[df_sub["处理情况"] != "待处理"]
    if len(df_solved) == 0:
        return 0
    return df_solved["处理时效"].mean()

# 看板切换
page_tab = st.radio("看板切换", ["全局异常总览看板", "边贡不足专项根因看板"])


# ===================== 页面1：全局异常总览看板（管理层使用） =====================
if page_tab == "全局异常总览看板":
    st.markdown("# 📊 采购链接异常全局监控看板")
    st.divider()

    # 计算当前区间指标
    # 1.总工单
    total_curr = len(df_curr_range)
    total_last = len(df_last_range)
    total_delta = calc_ratio(total_curr, total_last)

    # 2.边贡不足工单
    margin_curr = len(df_curr_range[df_curr_range["链接异常问题"] == "需更换（边贡不足）"])
    margin_last = len(df_last_range[df_last_range["链接异常问题"] == "需更换（边贡不足）"])
    margin_delta = calc_ratio(margin_curr, margin_last)

    # 3.链接失效工单
    link_fail_curr = len(df_curr_range[df_curr_range["链接异常问题"] == "需更换（链接失效）"])
    link_fail_last = len(df_last_range[df_last_range["链接异常问题"] == "需更换（链接失效）"])
    link_fail_delta = calc_ratio(link_fail_curr, link_fail_last)

    # 4.未解决工单
    unsolve_curr = len(df_curr_range[(df_curr_range["处理情况"] == "待处理")])
    unsolve_last = len(df_last_range[(df_last_range["处理情况"] == "待处理")])
    # unsolve_delta = calc_ratio(unsolve_curr, unsolve_last)

    # 5.平均处理时效(顶部已给出）
    avg_curr = get_avg_handle(df_curr_range)
    avg_last = get_avg_handle(df_last_range)
    avg_delta = calc_ratio(avg_curr, avg_last)

    # 6.SKU数量
    sku_curr = df_curr_range["sku"].nunique()
    sku_last = df_last_range["sku"].nunique()
    sku_delta = calc_ratio(sku_curr, sku_last)

    # KPI指标卡
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric(label="总异常工单量", value=total_curr, delta=total_delta, delta_color="inverse")
    with c2:
        st.metric(label="边贡不足工单", value=margin_curr, delta=margin_delta, delta_color="inverse")
    with c3:
        st.metric(label="链接失效工单", value=link_fail_curr, delta=link_fail_delta, delta_color="inverse")
    with c4:
        st.metric(label="未解决工单", value=unsolve_curr)
        # st.metric(label="未解决工单", value=unsolve_curr, delta=unsolve_delta, delta_color="inverse")
    with c5:
        st.metric(label="平均处理时效(天)", value=f"{avg_curr:.1f}", delta=avg_delta, delta_color="inverse")
    with c6:
        st.metric(label="涉及独立SKU", value=sku_curr, delta=sku_delta, delta_color="inverse")

    st.info(f"""环比对比：当前筛选区间 {curr_label}  VS 上期同等时长区间 {last_label}数值上升标红（指标恶化），数值下降标绿（指标改善）""")
    st.divider()

    # 每日趋势柱状图 数据源df_curr_range（筛选区间）
    st.subheader("📈 筛选区间每日新增异常工单趋势")
    day_df = df_curr_range.groupby(["创建时间", "链接异常问题"]).size().reset_index(name="工单数量")
    fig_bar = px.bar(
        day_df,
        x="创建时间",
        y="工单数量",
        color="链接异常问题",
        barmode="stack",
        height=400
    )
    fig_bar.update_traces(texttemplate="%{y}", textposition="outside", textfont_size=10)
    fig_bar.update_layout(legend_font_size=8, margin={"t": 40})
    st.plotly_chart(fig_bar, use_container_width=True)
    st.divider()

    # 环形图+负责人TOP10 数据源df_curr_range
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🥧 异常工单类型分布")
        pie_df = df_curr_range.groupby("链接异常问题").size().reset_index(name="工单数量")
        fig_pie = px.pie(pie_df, names="链接异常问题", values="工单数量", hole=0.4, height=450)
        fig_pie.update_traces(texttemplate="%{value}条\n%{percent:.1%}", textfont_size=11)
        fig_pie.update_layout(legend_font_size=9)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_right:
        st.subheader("🏆 筛选区间负责人异常工单TOP10")
        top_user = df_curr_range.groupby("负责人").size().reset_index(name="工单数量").sort_values("工单数量", ascending=False).head(10)
        fig_rank = px.bar(top_user, x="工单数量", y="负责人", orientation="h", height=450)
        st.plotly_chart(fig_rank, use_container_width=True)
    st.divider()

    # 负责人汇总表
    st.subheader("📋 各负责人异常汇总明细")
    def count_margin(x):
        return (x == "需更换（边贡不足）").sum()
    pivot_user = df_curr_range.groupby("负责人").agg(
        总工单=("订单号", "count"),
        边贡不足工单=("链接异常问题", count_margin),
        未解决工单=("处理情况", lambda x: (x == "待处理").sum()),
        # 仅统计处理情况不是待处理的工单时效，剔除0值，和顶部KPI统一口径
        平均处理时效=("处理时效", lambda ser: ser[df_curr_range.loc[ser.index, "处理情况"] != "待处理"].mean())
    ).reset_index()
    pivot_user["边贡异常占比"] = (pivot_user["边贡不足工单"] / pivot_user["总工单"]).apply(lambda x: f"{x:.2%}")
    st.dataframe(pivot_user, use_container_width=True)





# ===================== 页面2：边贡不足专项根因看板（仅筛选链接异常=需更换(边贡不足)的数据） =====================
if page_tab == "边贡不足专项根因看板":
    st.markdown("# 🔍 边贡不足异常专项根因深度分析看板")
    st.divider()

    # 当前筛选区间内的边贡数据
    df_margin_curr = df_curr_range[df_curr_range["链接异常问题"] == "需更换（边贡不足）"]
    # 上期对比区间内的边贡数据
    df_margin_last = df_last_range[df_last_range["链接异常问题"] == "需更换（边贡不足）"]

    # 复制临时表
    df_margin_temp = df_margin_curr.copy()

    # 修复函数：全部去空格匹配，避免空格导致匹配失败
    def fix_operator_name(row):
        op = str(row["运营"]).strip()
        owner = str(row["负责人"]).strip()
        if op == "未分配人员" and owner == "张亚伦":
            return "张亚伦"
        return row["运营"]

    df_margin_temp["运营"] = df_margin_temp.apply(fix_operator_name, axis=1)

    # 生成展示时效列，同样去空格匹配待处理
    df_margin_temp["展示时效"] = df_margin_temp.apply(
        lambda r: 0 if str(r["处理情况"]).strip() == "待处理" else r["处理时效"],
        axis=1
    )

    # 新增：过滤掉所有运营未分配人员脏数据
    # df_margin_temp = df_margin_temp[df_margin_temp["运营"].str.strip() != "未分配人员"]

    # KPI计算
    total_m_curr = len(df_margin_curr)
    total_m_last = len(df_margin_last)
    top_root_curr = len(df_margin_curr[df_margin_curr["边贡不足无法采购原因"] == "链接毛利不足"])
    top_root_last = len(df_margin_last[df_margin_last["边贡不足无法采购原因"] == "链接毛利不足"])
    unsolve_m_curr = len(df_margin_curr[(df_margin_curr["处理情况"] == "待处理")])
    unsolve_m_last = len(df_margin_last[(df_margin_last["处理情况"] == "待处理")])

    delta_total = calc_ratio(total_m_curr, total_m_last)
    delta_root = calc_ratio(top_root_curr, top_root_last)
    ratio_text = f"{total_m_curr / len(df_curr_range):.2%}"

    # KPI卡片
    k1, k2, k3, k4 = st.columns(4)
    with k1: st.metric("边贡不足工单总数", total_m_curr, delta=delta_total, delta_color="inverse")
    with k2: st.metric("占全部工单比例", ratio_text)
    with k3: st.metric("链接毛利不足工单", top_root_curr, delta=delta_root, delta_color="inverse")
    with k4: st.metric("未闭环边贡工单", unsolve_m_curr)

    st.info(f"环比对比：当前筛选区间 {curr_label} VS 上期同等时长区间 {last_label}")
    st.divider()

    # 每日趋势图
    st.subheader("📈 边贡不足各类根因每日新增趋势")
    day_root_df = df_margin_curr.groupby(["创建时间", "边贡不足无法采购原因"]).size().reset_index(name="工单数量")
    fig_day = px.bar(day_root_df, x="创建时间", y="工单数量", color="边贡不足无法采购原因", barmode="stack", height=400)
    fig_day.update_traces(texttemplate="%{y}", textposition="outside", textfont_size=9)
    fig_day.update_layout(legend_font_size=8, margin={"t": 40})
    st.plotly_chart(fig_day, use_container_width=True)
    st.divider()

    # 环形图+负责人透视表（数据源df_margin_temp）
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🥧 边贡不足原因分布")
        root_df = df_margin_curr.groupby("边贡不足无法采购原因").size().reset_index(name="工单数量")
        fig_root = px.pie(root_df, names="边贡不足无法采购原因", values="工单数量", hole=0.4, height=480)
        fig_root.update_traces(texttemplate="%{value}条 / %{percent:.1%}", textfont_size=12)
        fig_root.update_layout(legend_font_size=10)
        st.plotly_chart(fig_root, use_container_width=True)
    with col_b:
        # ========== 重点修复：删除重复copy临时表代码，直接复用上方df_margin_temp ==========
        # 透视表使用新建的「展示时效」
        pivot_table = pd.pivot_table(
            df_margin_temp,
            index="负责人",
            columns="边贡不足无法采购原因",
            values="订单号",
            aggfunc="count",
            fill_value=0
        )
        # 工单合计放在姓名后、根因前列
        pivot_table["工单合计"] = pivot_table.sum(axis=1)
        new_cols = ["工单合计"] + list(pivot_table.columns.drop("工单合计"))
        pivot_table = pivot_table[new_cols]

        # 新增平均处理时效列（和负责人表逻辑一致）
        avg_ser = df_margin_temp.groupby("负责人")["展示时效"].mean()
        pivot_table["平均处理时效"] = avg_ser
        st.dataframe(pivot_table, use_container_width=True)
    st.divider()

    # 运营TOP10+明细
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.subheader("📊 运营 × 边贡不足根因透视表")
        pivot_operator = pd.pivot_table(
            df_margin_temp,
            index="运营",
            columns="边贡不足无法采购原因",
            values="订单号",
            aggfunc="count",
            fill_value=0
        )
        pivot_operator["工单合计"] = pivot_operator.sum(axis=1)
        new_op_cols = ["工单合计"] + list(pivot_operator.columns.drop("工单合计"))
        pivot_operator = pivot_operator[new_op_cols]
        op_avg_time = df_margin_temp.groupby("运营")["展示时效"].mean()
        pivot_operator["平均处理时效"] = op_avg_time
        st.dataframe(pivot_operator, use_container_width=True)
    with col_s2:
        st.subheader("🏆 高风险运营TOP10")
        risk_operator_df = df_margin_temp.groupby("运营").size().reset_index(name="工单数量").sort_values(by="工单数量",
                                                                                                          ascending=False).head(
            10)
        fig_risk_op = px.bar(
            risk_operator_df,
            x="工单数量",
            y="运营",
            orientation="h",
            height=420,
            text="工单数量"  # 绑定显示数值
        )
        # 开启文字展示、调整大小位置
        fig_risk_op.update_traces(
            texttemplate="%{text}",
            textposition="outside",
            textfont_size=11
        )
        st.plotly_chart(fig_risk_op, use_container_width=True)

    st.subheader("📋 运营及负责人边贡工单明细")
    display_cols = ["创建时间", "运营", "负责人", "sku", "商品中文名称（运营填）", "供应商名称（运营填）", "商品成本",
                    "重量（采购填）", "边贡不足无法采购原因", "处理情况", "处理时效", "已解决"]
    # 明细表格同步使用处理后的临时表
    detail_df = df_margin_temp[display_cols].sort_values("创建时间", ascending=False)
    st.dataframe(detail_df, use_container_width=True)
