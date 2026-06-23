import pandas as pd
from sqlalchemy import create_engine
import os
import streamlit as st
base_path = os.path.dirname(__file__)
# ===================== 配置区，修改MySQL账号密码 =====================
# MYSQL_USER = "root"
# MYSQL_PWD = "123456"
# MYSQL_HOST = "127.0.0.1"
# MYSQL_PORT = "3306"
# DB_NAME = "purchase_link_abnormal"

MYSQL_USER = st.secrets["MYSQL_USER"]
MYSQL_PWD = st.secrets["MYSQL_PWD"]
MYSQL_HOST = st.secrets["MYSQL_HOST"]
MYSQL_PORT = st.secrets["MYSQL_PORT"]
DB_NAME = st.secrets["MYSQL_DB"]
EXCEL_PATH = os.path.join(base_path, "采购链接异常处理表.xlsx")  # 钉钉导出的Excel文件路径
# ========================================================================

# 1. 连接MySQL
engine = create_engine(f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PWD}@{MYSQL_HOST}:{MYSQL_PORT}/{DB_NAME}")

# 2. 读取Excel原始采购数据
df = pd.read_excel(EXCEL_PATH)

# 3. 基础清洗：订单号去重、填充空值
df["链接异常问题"] = df["链接异常问题"].fillna("未标注异常类型")
df["订单号"] = df["订单号"].fillna("null")
df["边贡不足无法采购原因"] = df["边贡不足无法采购原因"].fillna("无细分原因")
df["运营"] = df["运营"].fillna("未分配人员")
df["组长"] = df["组长"].fillna("未分配人员")
df["负责人"] = df["负责人"].fillna("未分配人员")
df["处理情况"] = df["处理情况"].fillna("待处理")
df["商品中文名称（运营填）"] = df["商品中文名称（运营填）"].fillna("未填写商品中文名称")
df["供应商名称（运营填）"] = df["供应商名称（运营填）"].fillna("未填写供应商")
df["商品链接（运营填）"] = df["商品链接（运营填）"].fillna("未填写商品链接")
df["商品成本"] = df["商品成本"].fillna(0)
df["成本（采购填）"] = df["成本（采购填）"].fillna(0)
df["重量（采购填）"] = df["重量（采购填）"].fillna(0)
df["备注"] = df["备注"].fillna("无")
df["处理时效"] = df["处理时效"].fillna(0)
df["已解决"] = df["已解决"].fillna(0)

# 4. 转换时间字段为标准日期格式
df["创建时间"] = pd.to_datetime(df["创建时间"], errors="coerce").dt.date
df["更新时间"] = pd.to_datetime(df["更新时间"], errors="coerce").dt.date

# 5. 自动生成【异常大类】字段，写入数据库新列
def get_abnormal_type(text):
    text = str(text).strip()
    if "需更换（边贡不足）" in text:
        return "需更换（边贡不足）"
    elif "需更换（链接失效）" in text:
        return "需更换（链接失效）"
    elif "需更换（供应商异常）" in text:
        return "需更换（供应商异常）"
    elif "需更换（起批量异常）" in text:
        return "需更换（起批量异常）"
    elif "超重/尺寸不在采购" in text:
        return "超重/尺寸不在采购"
    elif "超重，跳物流（不换链接）" in text:
        return "超重，跳物流（不换链接）"
    elif "货不对板" in text:
        return "货不对板"
    elif "敏感货不予采购" in text:
        return "敏感货不予采购"
    else:
        return "其他异常"
df["异常大类"] = df["链接异常问题"].apply(get_abnormal_type)

# 6. 自动生成【边贡细分根因】字段
# 【替换原有get_margin_cause函数】
def get_margin_cause(row):
    # 非边贡类工单统一标记
    if row["异常大类"] != "需更换（边贡不足）":
        return "非边贡类异常"
    reason = str(row["边贡不足无法采购原因"]).strip()
    if reason == "链接毛利不足":
        return "链接毛利本身不足"
    elif reason == "出库重量增加导致边贡不足":
        return "出库重量上涨，物流成本超标"
    elif reason == "供应商涨价":
        return "供应商调价，采购成本上涨"
    elif reason == "价格贴近百25 打包后毛利不足":
        return "打包后毛利贴近阈值25%不足"
    elif reason == "前端被加活动":
        return "平台前端活动降价压缩毛利"
    elif reason == "多pc商品售卖1pc导致运费增加":
        return "单卖拆分商品，单位运费抬高"
    else:
        return "其他毛利压缩因素"
df["边贡细分根因"] = df.apply(get_margin_cause, axis=1)

# 7. 数据写入你现有的表：采购链接异常处理表
df.to_sql(
    name="采购链接异常处理表",
    con=engine,
    if_exists="replace",  # 覆盖更新全量数据；增量导入改为append
    index=False,
    chunksize=1000
)
print(f"数据入库完成，共{len(df)}条工单已写入【采购链接异常处理表】")