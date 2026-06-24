import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, true

# ===================== MySQL数据库配置 =====================

# 从Streamlit后台密钥读取数据库信息
MYSQL_USER = "FZXqgY12HpKGyKh.root"
MYSQL_PWD = "5kFyPsP4D61d5syZ"
MYSQL_HOST = "gateway01.ap-southeast-1.prod.aws.tidbcloud.com"
MYSQL_PORT = 4000
DB_NAME = "link_abnormal_db"

engine = create_engine(f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PWD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}")
# ==========================================================

# 页面全局基础配置
st.set_page_config(page_title="Ozon采购链接异常分析看板", layout="wide")

# ===================== 新增：全局缓存函数，解决重复查库、重复分组卡顿 =====================
@st.cache_data(ttl=300)
def load_full_data():
    sql_query = "SELECT * FROM `采购链接异常处理表`;"
    df = pd.read_sql(sql_query, con=engine)
    df["创建时间"] = pd.to_datetime(df["创建时间"])
    return df

@st.cache_data(ttl=300)
def filter_date_range(df_all, s_dt, e_dt):
    df_sub = df_all[(df_all["创建时间"] >= s_dt) & (df_all["创建时间"] <= e_dt)]
    return df_sub

@st.cache_data(ttl=300)
def get_leader_summary(df_curr):
    def count_margin(x):
        return (x == "需更换（边贡不足）").sum()
    pivot_user = df_curr.groupby("负责人").agg(
        总工单=("订单号", "count"),
        边贡不足工单=("链接异常问题", count_margin),
        未解决工单=("处理情况", lambda x: (x == "待处理").sum()),
        平均处理时效=("处理时效", lambda ser: ser[df_curr.loc[ser.index, "处理情况"] != "待处理"].mean())
    ).reset_index()
    pivot_user["边贡异常占比"] = (pivot_user["边贡不足工单"] / pivot_user["总工单"]).apply(lambda x: f"{x:.2%}")
    pivot_user = pivot_user.sort_values(by="总工单", ascending=False).reset_index(drop=True)
    pivot_user["占比数值"] = pivot_user["边贡异常占比"].str.rstrip("%").astype(float)
    return pivot_user

@st.cache_data(ttl=300)
def get_sub_leader_detail(df_curr, target_leader):
    def count_margin(x):
        return (x == "需更换（边贡不足）").sum()
    sub_data = df_curr[df_curr["负责人"] == target_leader]
    sub_group = sub_data.groupby(["运营", "组长"]).agg(
        总工单=("订单号", "count"),
        边贡不足工单=("链接异常问题", count_margin)
    ).reset_index()
    sub_group = sub_group.sort_values("总工单", ascending=False).reset_index(drop=True)
    sub_group["排名"] = sub_group.index + 1
    return sub_group

# ===================== 缓存加载全量数据，只查一次库 =====================
df_all = load_full_data()

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
df_curr_range = filter_date_range(df_all, start_dt, end_dt)

# 2、自动计算上一个同等长度区间（仅用于KPI环比对比）
range_days = (end_dt - start_dt).days + 1
last_end_dt = start_dt - pd.Timedelta(days=1)
last_start_dt = last_end_dt - pd.Timedelta(days=range_days - 1)
df_last_range = filter_date_range(df_all, last_start_dt, last_end_dt)

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
    # ========= KPI模块数据分析 =========
    margin_ratio = margin_curr / total_curr
    st.info(f"""【KPI核心结论】
1. 当前周期总异常工单{total_curr}单，边贡不足工单占比{margin_ratio:.1%}，是核心异常类型；
2. 待处理存量{unsolve_curr}单，平均处理时效{avg_curr:.1f}天，处理效率整体良好；
3. 链接失效工单环比{link_fail_delta}，相比边贡不足问题风险更小。""")
    st.divider()

    # 每日趋势柱状图 数据源df_curr_range（筛选区间）
    st.subheader("📈 每日新增异常工单趋势")
    day_df = df_curr_range.groupby(["创建时间", "链接异常问题"]).size().reset_index(name="工单数量")
    fig_bar = px.bar(
        day_df,
        x="创建时间",
        y="工单数量",
        color="链接异常问题",
        barmode="stack",
        height=400
    )
    fig_bar.update_traces(texttemplate="%{y}", textposition="outside", textfont_size=12)
    fig_bar.update_layout(legend_font_size=12, margin={"t": 40})
    st.plotly_chart(fig_bar, use_container_width=True)
    # ========= 每日趋势模块数据分析 =========
    day_total = day_df.groupby("创建时间")["工单数量"].sum()
    max_day_num = day_total.max()
    max_day_dt = day_total.idxmax()
    st.info(f"""【每日趋势结论】
周期内工单峰值日期：{max_day_dt.strftime('%Y-%m-%d')}，单日最高异常{max_day_num}单；
每日工单结构稳定，边贡不足为每日主要新增异常，无单日结构性突变。""")
    st.divider()

    # 环形图+负责人TOP10 数据源df_curr_range
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🍩 异常工单类型分布")
        pie_df = df_curr_range.groupby("链接异常问题").size().reset_index(name="工单数量")
        fig_pie = px.pie(pie_df, names="链接异常问题", values="工单数量", hole=0.4, height=450)
        fig_pie.update_traces(texttemplate="%{value}条\n%{percent:.1%}", textfont_size=11)
        fig_pie.update_layout(legend_font_size=11)
        st.plotly_chart(fig_pie, use_container_width=True)
        # ========= 环形图模块分析 =========
        top_type = pie_df.iloc[pie_df["工单数量"].idxmax()]
        st.info(f"""【异常类型结论】
占比最高异常：{top_type['链接异常问题']}，工单{top_type['工单数量']}条，占全部异常{top_type['工单数量']/total_curr:.1%}；
其余类型工单占比低，治理重心集中于边贡不足问题。""")
    with col_right:
        st.subheader("🏆 负责人异常工单TOP10")
        # 1. 先按工单数量降序排序，保证从上到下数量递减
        top_user = df_curr_range.groupby("负责人").size().reset_index(name="工单数量")
        top_user = top_user.sort_values(by="工单数量", ascending=True)  # 升序，绘图后顶部是最大值

        # 2. 新增颜色区分：前3名橙色高亮，其余灰色
        def color_label(val):
            if val >= top_user["工单数量"].nlargest(3).min():
                return "#ff7800"  # 高亮橙
            else:
                return "#6688bb"  # 普通蓝灰

        top_user["条形颜色"] = top_user["工单数量"].apply(color_label)

        fig_rank = px.bar(
            top_user,
            x="工单数量",
            y="负责人",
            orientation="h",
            height=450,
            text="工单数量",  # 绑定数值展示
            color="条形颜色",
            color_discrete_map="identity"  # 使用自定义颜色列
        )
        # 3. 条形外侧展示数字，调整字体大小
        fig_rank.update_traces(
            texttemplate="%{text}",
            textposition="outside",
            textfont_size=10
        )
        # 隐藏图例（颜色仅区分，无需图例）
        fig_rank.update_layout(showlegend=False)
        st.plotly_chart(fig_rank, use_container_width=True)
        # ========= 负责人TOP10分析 =========
        top3_user = top_user.nlargest(3, "工单数量")
        top3_sum = top3_user["工单数量"].sum()
        st.info(f"""【负责人排行结论】
工单高度集中前3人，工单前三名负责人合计{top3_sum}单，占全部异常{top3_sum/total_curr:.1%}；
标记人员需重点跟进。""")
    st.divider()

    # ++++++++++++++++负责人汇总表+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # 负责人汇总表
    st.subheader("📋 各负责人异常汇总明细")
    def count_margin(x):
        return (x == "需更换（边贡不足）").sum()

    # 初始化选中负责人缓存
    if "select_leader" not in st.session_state:
        st.session_state.select_leader = ""

    # ===================== 修改：调用缓存聚合函数，不再实时groupby =====================
    pivot_user = get_leader_summary(df_curr_range)

    # 临时列用于高亮筛选
    top3_total_rows = set(pivot_user.head(3).index)
    low3_ratio_rows = set(pivot_user.nsmallest(3, "占比数值").index)
    # 行高亮样式函数
    def highlight_style(row):
        row_idx = row.name
        cols_len = len(row)
        if row_idx in top3_total_rows:
            return ["background-color: #fff3cd"] * cols_len
        if row_idx in low3_ratio_rows:
            return ["background-color: #e7f5ff"] * cols_len
        return [""] * cols_len
    # 渲染主表格（纯展示，无内置按钮）
    show_df = pivot_user.drop(columns="占比数值").copy()
    styled_table = show_df.style.apply(highlight_style, axis=1)
    st.dataframe(styled_table, use_container_width=True)
    # ========= 负责人明细表格分析 =========
    max_handle = pivot_user["平均处理时效"].max()
    max_handle_name = pivot_user.loc[pivot_user["平均处理时效"].idxmax(), "负责人"]
    st.info(f"""【负责人明细结论】
{max_handle_name}平均处理时效{max_handle:.2f}天，全组处理最慢；
浅橙行：工单数量前三负责人；浅蓝行：边贡异常占比最低3人，边贡问题压力更小，可以详细了解为什么比他人占比低这么多。""")

    # ========== 替代点击：下拉选择框，稳定触发弹窗 ==========
    all_leader_list = pivot_user["负责人"].tolist()
    choose_leader = st.selectbox("选择负责人查看下属运营/组长明细", ["请选择负责人"] + all_leader_list)
    # 选中后更新缓存
    if choose_leader != "请选择负责人":
        st.session_state.select_leader = choose_leader
    # ========== 弹窗详情面板 ==========
    if st.session_state.select_leader != "":
        st.divider()
        with st.container(border=True):
            st.header(f"🔎 {st.session_state.select_leader} 下属运营&组长工单明细")
            # ===================== 修改：调用缓存明细函数 =====================
            sub_group = get_sub_leader_detail(df_curr_range, st.session_state.select_leader)
            # 展示明细表格
            st.dataframe(sub_group, use_container_width=True)
            # ========= 下属明细分析 =========
            sub_total = sub_group["总工单"].sum()
            sub_top1 = sub_group.iloc[0]
            st.info(f"""【下属明细结论】
该负责人下全部工单合计{sub_total}单；
排名1运营{sub_top1['运营']}工单量{sub_top1['总工单']}，是该负责人下主要异常来源。""")
            # 清空选择按钮
            if st.button("关闭当前明细"):
                st.session_state.select_leader = ""
                # 删除st.rerun() 减少强制刷新卡顿

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
    top_root_last = len(df_margin_last[df_last_range["边贡不足无法采购原因"] == "链接毛利不足"])
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
    # ========= 边贡专项KPI分析 =========
    root_ratio = top_root_curr / total_m_curr
    st.info(f"""【边贡专项KPI结论】
1. 边贡工单环比{delta_total}，整体良好；
2. 链接毛利不足占全部边贡工单{root_ratio:.1%}，是核心根因；""")
    st.divider()

    # 每日趋势图
    st.subheader("📈 边贡不足各类根因每日新增趋势")
    print("   "
          "")
    day_root_df = df_margin_curr.groupby(["创建时间", "边贡不足无法采购原因"]).size().reset_index(name="工单数量")
    fig_day = px.bar(day_root_df, x="创建时间", y="工单数量", color="边贡不足无法采购原因", barmode="stack", height=400)
    fig_day.update_traces(texttemplate="%{y}", textposition="outside", textfont_size=9)
    fig_day.update_layout(legend_font_size=8, margin={"t": 40})
    st.plotly_chart(fig_day, use_container_width=True)
    # ========= 边贡每日趋势分析 =========
    day_m_total = day_root_df.groupby("创建时间")["工单数量"].sum()
    m_peak_day = day_m_total.idxmax()
    m_peak_num = day_m_total.max()
    st.info(f"""【边贡每日趋势结论】
周期内边贡工单峰值：{m_peak_day.strftime('%Y-%m-%d')}，单日{m_peak_num}单；
每日结构稳定，毛利不足始终为每日主要诱因。""")
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
        # ========= 根因环形图分析 =========
        top_root_item = root_df.iloc[root_df["工单数量"].idxmax()]
        # 统计空白根因工单数量
        blank_root_count = len(df_margin_curr[df_margin_curr["边贡不足无法采购原因"].isna() | (
                    df_margin_curr["边贡不足无法采购原因"] == "无细分原因")])
        st.info(f"""【根因分布结论】
最大诱因：{top_root_item['边贡不足无法采购原因']}，工单{top_root_item['工单数量']}条；
其余涨价、重量超标、活动影响工单占比较低，次要风险。但需要注意的是无细分根因空白工单共{blank_root_count}条，需要运营以后补充填写异常原因。""")
    with col_b:
        # ========== 重点修复：删除重复copy临时表代码，直接复用上方df_margin_temp ==========
        # 透视表使用新建的「展示时效」
        st.subheader("📊 负责人 × 边贡不足根因透视表")
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

        # ========== 新增1：按工单合计从高到低排序 ==========
        pivot_table = pivot_table.sort_values(by="工单合计", ascending=False).reset_index()

        # ========== 新增2：工单数量前三名浅色高亮样式 ==========
        def highlight_top3_row(row):
            # 前3行（索引0、1、2）添加浅蓝背景，其余行无样式
            if row.name in [0, 1, 2]:
                return ["background-color: #f0f8ff"] * len(row)
            return [""] * len(row)

        # 生成带样式的表格
        styled_pivot_table = pivot_table.style.apply(highlight_top3_row, axis=1)
        # 渲染带样式的表格
        st.dataframe(styled_pivot_table, use_container_width=True)
        # ========= 负责人透视表分析 =========
        top3_leader_sum = pivot_table.head(3)["工单合计"].sum()
        st.info(f"""【负责人透视结论】
工单前三负责人边贡工单合计{top3_leader_sum}单，承担绝大部分边贡压力；
浅蓝行代表边贡工单负荷最高3人，需优先复盘其商品定价成本问题。""")
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
        # 工单合计列放在最前
        pivot_operator["工单合计"] = pivot_operator.sum(axis=1)
        new_op_cols = ["工单合计"] + list(pivot_operator.columns.drop("工单合计"))
        pivot_operator = pivot_operator[new_op_cols]
        # 新增平均处理时效列
        op_avg_time = df_margin_temp.groupby("运营")["展示时效"].mean()
        pivot_operator["平均处理时效"] = op_avg_time

        # ========== 新增1：按工单合计从高到低排序 ==========
        pivot_operator = pivot_operator.sort_values(by="工单合计", ascending=False).reset_index()

        # ========== 新增2：工单数量前三名浅色高亮（和负责人表颜色区分，用浅橙色） ==========
        def highlight_top3_operation(row):
            # 前3行（索引0、1、2）添加浅橙背景，和负责人表的浅蓝做区分
            if row.name in [0, 1, 2]:
                return ["background-color: #fff3cd"] * len(row)
            return [""] * len(row)

        # 生成带样式的表格
        styled_pivot_op = pivot_operator.style.apply(highlight_top3_operation, axis=1)
        # 渲染带样式的表格
        st.dataframe(styled_pivot_op, use_container_width=True)
        # ========= 运营透视表分析 =========
        top1_op = pivot_operator.iloc[0]
        st.info(f"""【运营透视结论】
异常量最高运营：{top1_op['运营']}，边贡工单{top1_op['工单合计']}单，远超其他运营；
浅橙三行为高风险运营，其商品链路毛利模型存在批量异常。第二、第三位异常链接甚至超过了某几个个部门的总量，重点关注跟进""")
    with col_s2:
        st.subheader("🏆 高风险运营TOP10")
        # 先升序排序，绘图后最大的行会显示在最上方
        risk_operator_df = df_margin_temp.groupby("运营").size().reset_index(name="工单数量")
        risk_operator_df = risk_operator_df.sort_values(by="工单数量", ascending=True).tail(10)

        fig_risk_op = px.bar(
            risk_operator_df,
            x="工单数量",
            y="运营",
            orientation="h",
            height=420,
            text="工单数量"  # 绑定显示数值
        )
        # 开启文字展示、调整大小位置（修改textfont_size= 后面数字即可改字号）
        fig_risk_op.update_traces(
            texttemplate="%{text}",
            textposition="outside",
            textfont_size=13  # 数字字体大小，按需调大/调小
        )
        st.plotly_chart(fig_risk_op, use_container_width=True)
        # ========= 高风险运营TOP10分析 =========
        top_op_name = risk_operator_df.iloc[-1]["运营"]
        top_op_num = risk_operator_df.iloc[-1]["工单数量"]
        st.info(f"""【高风险运营排行结论】
TOP1运营{top_op_name}工单{top_op_num}单，断层领先其余运营（情况特殊），但其他人员值得注意。""")
    st.divider()

    st.subheader("📋 运营及负责人边贡工单明细")
    display_cols = ["创建时间", "运营", "组长","负责人", "sku", "商品中文名称（运营填）", "供应商名称（运营填）", "商品成本",
                    "重量（采购填）", "边贡不足无法采购原因", "处理情况", "处理时效", "已解决"]
    # 明细表格同步使用处理后的临时表
    detail_df = df_margin_temp[display_cols].sort_values("创建时间", ascending=False)
    st.dataframe(detail_df, use_container_width=True)
    # ========= 全量明细分析 =========
    unsolve_m_detail = len(detail_df[detail_df["处理情况"] == "待处理"])
    st.info(f"""【工单明细结论】
明细共{len(detail_df)}条边贡工单，未处理{unsolve_m_detail}条；
可筛选对应SKU/运营定位批量异常商品，针对性调价优化毛利。""")
