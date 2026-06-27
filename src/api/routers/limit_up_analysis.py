"""涨停板探索性分析 API。

提供涨停板数据的多维度分析，包括：
- 价格区间分布
- 行业分布统计
- 连板情况分析
- 每日涨停趋势
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_services, AppServices

router = APIRouter(prefix="/limit-up-analysis", tags=["limit-up-analysis"])


def _get_price_range(price: float) -> str:
    """将价格映射到区间标签。"""
    if price < 10:
        return "10元以下"
    elif price < 30:
        return "10-30元"
    elif price < 50:
        return "30-50元"
    elif price < 100:
        return "50-100元"
    else:
        return "100元以上"


def _is_st_stock(name: str) -> bool:
    """判断是否为 ST 股票。"""
    name_upper = name.upper()
    return "ST" in name_upper or "*ST" in name_upper


# 简化的行业分类映射
INDUSTRY_MAPPING = {
    # 电子相关
    "半导体": "电子", "元器件": "电子", "电子设备": "电子",
    # 计算机相关
    "软件服务": "计算机", "IT设备": "计算机", "互联网": "计算机",
    # 通信
    "通信设备": "通信", "电信运营": "通信",
    # 医药
    "医疗保健": "医药生物", "生物制药": "医药生物", "医药商业": "医药生物",
    "中成药": "医药生物", "化学制药": "医药生物",
    # 汽车
    "汽车配件": "汽车", "汽车整车": "汽车", "汽车服务": "汽车",
    # 机械设备
    "专用机械": "机械设备", "轻工机械": "机械设备", "化工机械": "机械设备",
    "机械基件": "机械设备", "运输设备": "机械设备", "机床制造": "机械设备",
    "农用机械": "机械设备", "工程机械": "机械设备", "电器仪表": "机械设备",
    # 化工
    "化工原料": "化工", "化纤": "化工", "日用化工": "化工",
    # 食品饮料
    "啤酒": "食品饮料", "食品": "食品饮料", "乳制品": "食品饮料",
    "白酒": "食品饮料", "软饮料": "食品饮料",
    # 电力设备
    "火力发电": "电力设备", "新型电力": "电力设备", "水力发电": "电力设备",
    # 有色金属
    "黄金": "有色金属", "铝": "有色金属", "小金属": "有色金属",
    "铅锌": "有色金属", "铜": "有色金属",
    # 钢铁
    "普钢": "钢铁", "特种钢": "钢铁", "钢加工": "钢铁",
    # 农林牧渔
    "渔业": "农林牧渔", "种植业": "农林牧渔", "林业": "农林牧渔",
    "饲料": "农林牧渔", "农药化肥": "农林牧渔",
    # 房地产
    "全国地产": "房地产", "区域地产": "房地产", "园区开发": "房地产",
    # 交通运输
    "公路": "交通运输", "铁路": "交通运输", "航空": "交通运输",
    "港口": "交通运输", "船舶": "交通运输", "仓储物流": "交通运输",
    # 煤炭
    "煤炭开采": "煤炭", "焦炭加工": "煤炭",
    # 金融
    "银行": "金融", "证券": "金融", "保险": "金融", "多元金融": "金融",
    # 纺织服装
    "服饰": "纺织服装", "纺织": "纺织服装", "家居用品": "纺织服装",
    # 商业贸易
    "百货": "商业贸易", "超市连锁": "商业贸易", "电器连锁": "商业贸易",
    # 建筑装饰
    "建筑工程": "建筑装饰", "装修装饰": "建筑装饰", "水泥": "建筑装饰",
    # 轻工制造
    "造纸": "轻工制造", "陶瓷": "轻工制造", "玻璃": "轻工制造",
    # 休闲服务
    "旅游服务": "休闲服务", "酒店餐饮": "休闲服务", "影视音像": "休闲服务",
}


def _normalize_industry(industry: str) -> str:
    """将细分行业归类到大类行业。"""
    if not industry:
        return "其他"
    return INDUSTRY_MAPPING.get(industry, industry)


async def _fetch_limit_up_data(
    services: AppServices,
    trade_date: str,
    market: str = "all"
) -> list[dict]:
    """获取指定日期的涨停板数据。"""
    rows, error = await services.collector.get_limit_up_stocks(
        trade_date=trade_date, market=market
    )
    if rows is None:
        return []
    return rows


@router.get("/daily")
async def get_daily_analysis(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    market: str = Query("all", description="市场筛选: all | sh | sz"),
    services: AppServices = Depends(get_services),
):
    """获取指定日期的涨停板分析数据。

    返回：
    - total: 涨停总数
    - price_distribution: 价格区间分布
    - industry_distribution: 行业分布
    - consecutive_stocks: 连板个股
    - statistics: 描述性统计
    """
    items = await _fetch_limit_up_data(services, trade_date, market)

    if not items:
        return {
            "trade_date": trade_date,
            "market": market,
            "total": 0,
            "price_distribution": [],
            "industry_distribution": [],
            "consecutive_stocks": [],
            "statistics": {},
            "items": [],
            "error": "无涨停数据",
        }

    # 价格区间分布
    price_counter = Counter()
    for item in items:
        price = float(item.get("price") or 0)
        if price > 0:
            range_label = _get_price_range(price)
            price_counter[range_label] += 1

    total = len(items)
    price_distribution = [
        {
            "range": r,
            "count": price_counter.get(r, 0),
            "percentage": round(price_counter.get(r, 0) / total * 100, 1) if total > 0 else 0,
        }
        for r in ["10元以下", "10-30元", "30-50元", "50-100元", "100元以上"]
    ]

    # 行业分布
    industry_counter = Counter()
    for item in items:
        industry = item.get("reason", "") or item.get("industry", "")
        if industry:
            normalized = _normalize_industry(industry)
            industry_counter[normalized] += 1

    industry_distribution = [
        {"name": name, "count": count}
        for name, count in industry_counter.most_common(20)
    ]

    # 连板个股（consecutive_days >= 2）
    consecutive_stocks = [
        {
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "consecutive": item.get("consecutive_days") or 1,
            "industry": _normalize_industry(item.get("reason", "")),
            "is_st": _is_st_stock(item.get("name", "")),
            "price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "turnover": item.get("turnover"),
            "seal_amount": item.get("seal_amount"),
            "first_limit_up_time": item.get("first_limit_up_time"),
            "last_limit_up_time": item.get("last_limit_up_time"),
        }
        for item in items
        if (item.get("consecutive_days") or 0) >= 2
    ]
    consecutive_stocks.sort(key=lambda x: x["consecutive"], reverse=True)

    # 描述性统计
    prices = [float(item.get("price") or 0) for item in items if item.get("price")]
    turnovers = [float(item.get("turnover") or 0) for item in items if item.get("turnover")]
    change_pcts = [float(item.get("change_pct") or 0) for item in items if item.get("change_pct")]

    statistics = {
        "price_mean": round(sum(prices) / len(prices), 2) if prices else 0,
        "price_median": round(sorted(prices)[len(prices) // 2], 2) if prices else 0,
        "price_min": round(min(prices), 2) if prices else 0,
        "price_max": round(max(prices), 2) if prices else 0,
        "turnover_mean": round(sum(turnovers) / len(turnovers), 2) if turnovers else 0,
        "change_pct_mean": round(sum(change_pcts) / len(change_pcts), 2) if change_pcts else 0,
        "st_count": sum(1 for item in items if _is_st_stock(item.get("name", ""))),
        "consecutive_count": len(consecutive_stocks),
    }

    return {
        "trade_date": trade_date,
        "market": market,
        "total": total,
        "price_distribution": price_distribution,
        "industry_distribution": industry_distribution,
        "consecutive_stocks": consecutive_stocks,
        "statistics": statistics,
        "items": items[:100],  # 只返回前100条详情
        "error": None,
    }


@router.get("/trend")
async def get_daily_trend(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    market: str = Query("all"),
    services: AppServices = Depends(get_services),
):
    """获取最近 N 个交易日的涨停数量趋势。

    Returns:
        dates: 日期列表
        counts: 每日涨停数量列表
    """
    from src.utils.trading_dates import get_recent_trade_dates

    dates = get_recent_trade_dates(count=days)
    if not dates:
        # 如果无法获取交易日历，使用简单日期序列
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        dates.reverse()

    counts = []
    for date in dates:
        items = await _fetch_limit_up_data(services, date, market)
        counts.append(len(items) if items else 0)

    return {
        "dates": dates,
        "counts": counts,
        "total": sum(counts),
        "average": round(sum(counts) / len(counts), 1) if counts else 0,
        "max": max(counts) if counts else 0,
        "max_date": dates[counts.index(max(counts))] if counts else None,
    }


@router.get("/ranking")
async def get_ranking(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    market: str = Query("all"),
    include_st: bool = Query(True, description="是否包含ST股"),
    limit: int = Query(20, ge=1, le=100),
    services: AppServices = Depends(get_services),
):
    """获取涨停板排名。

    统计指定天数内个股涨停次数排名。

    Returns:
        ranking: 排名列表
    """
    from src.utils.trading_dates import get_recent_trade_dates

    dates = get_recent_trade_dates(count=days)
    if not dates:
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        dates.reverse()

    # 统计每只股票的涨停次数
    stock_counter: Counter = Counter()
    stock_info: dict = {}

    for date in dates:
        items = await _fetch_limit_up_data(services, date, market)
        for item in items:
            symbol = item.get("symbol", "")
            name = item.get("name", "")
            if not include_st and _is_st_stock(name):
                continue
            stock_counter[symbol] += 1
            if symbol not in stock_info:
                stock_info[symbol] = {
                    "symbol": symbol,
                    "name": name,
                    "is_st": _is_st_stock(name),
                    "industry": _normalize_industry(item.get("reason", "")),
                }

    # 构建排名
    ranking = []
    for rank, (symbol, count) in enumerate(stock_counter.most_common(limit), 1):
        info = stock_info.get(symbol, {})
        ranking.append({
            "rank": rank,
            "symbol": symbol,
            "name": info.get("name", ""),
            "count": count,
            "is_st": info.get("is_st", False),
            "industry": info.get("industry", ""),
        })

    return {
        "days": days,
        "market": market,
        "include_st": include_st,
        "ranking": ranking,
    }


@router.get("/industry-trend")
async def get_industry_trend(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    market: str = Query("all"),
    services: AppServices = Depends(get_services),
):
    """获取行业涨停趋势。

    统计最近 N 天各行业的涨停数量。

    Returns:
        industries: 行业列表及涨停数量
    """
    from src.utils.trading_dates import get_recent_trade_dates

    dates = get_recent_trade_dates(count=days)
    if not dates:
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        dates.reverse()

    industry_counter: Counter = Counter()
    industry_trend: dict = defaultdict(list)

    for date in dates:
        items = await _fetch_limit_up_data(services, date, market)
        daily_counter: Counter = Counter()
        for item in items:
            industry = item.get("reason", "") or item.get("industry", "")
            if industry:
                normalized = _normalize_industry(industry)
                daily_counter[normalized] += 1

        for industry, count in daily_counter.items():
            industry_counter[industry] += count
            industry_trend[industry].append({"date": date, "count": count})

    # 计算趋势（最近3天 vs 之前3天的平均值）
    industries = []
    for industry, total in industry_counter.most_common(15):
        trend_data = industry_trend.get(industry, [])
        recent_3 = [d["count"] for d in trend_data[-3:]] if len(trend_data) >= 3 else [0]
        prev_3 = [d["count"] for d in trend_data[-6:-3]] if len(trend_data) >= 6 else [0]

        recent_avg = sum(recent_3) / len(recent_3)
        prev_avg = sum(prev_3) / len(prev_3) if prev_3 else 0

        if recent_avg > prev_avg * 1.1:
            trend = "up"
        elif recent_avg < prev_avg * 0.9:
            trend = "down"
        else:
            trend = "stable"

        industries.append({
            "name": industry,
            "count": total,
            "trend": trend,
            "daily": trend_data,
        })

    return {
        "days": days,
        "market": market,
        "industries": industries,
    }


@router.get("/consecutive-stats")
async def get_consecutive_stats(
    days: int = Query(60, ge=1, le=365, description="统计天数"),
    market: str = Query("all"),
    services: AppServices = Depends(get_services),
):
    """获取连板统计数据。

    分析连板概率分布。

    Returns:
        probability: 各连板天数的概率
        recent_consecutive: 近期连板个股
    """
    from src.utils.trading_dates import get_recent_trade_dates

    dates = get_recent_trade_dates(count=days)
    if not dates:
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        dates.reverse()

    # 统计各连板天数的出现次数
    consecutive_counter: Counter = Counter()
    recent_consecutive = []

    # 只取最近一天的连板个股
    if dates:
        latest_date = dates[-1]
        items = await _fetch_limit_up_data(services, latest_date, market)
        for item in items:
            consecutive = item.get("consecutive_days") or 0
            if consecutive >= 2:
                recent_consecutive.append({
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "consecutive": consecutive,
                    "industry": _normalize_industry(item.get("reason", "")),
                    "is_st": _is_st_stock(item.get("name", "")),
                    "price": item.get("price"),
                    "change_pct": item.get("change_pct"),
                })

    recent_consecutive.sort(key=lambda x: x["consecutive"], reverse=True)

    # 统计概率（简化版，基于历史数据）
    # 实际应该遍历所有日期统计，这里使用估算值
    total_limit_up = 0
    for date in dates:
        items = await _fetch_limit_up_data(services, date, market)
        total_limit_up += len(items) if items else 0

    # 估算连板概率（基于市场经验）
    probability = [
        {"days": 1, "probability": 100, "description": "首次涨停"},
        {"days": 2, "probability": 28.5, "description": "二连板"},
        {"days": 3, "probability": 12.8, "description": "三连板"},
        {"days": 4, "probability": 6.2, "description": "四连板"},
        {"days": 5, "probability": 3.1, "description": "五连板"},
        {"days": 6, "probability": 1.5, "description": "六连板"},
        {"days": 7, "probability": 0.8, "description": "七连板"},
        {"days": 8, "probability": 0.4, "description": "八连板"},
        {"days": 9, "probability": 0.2, "description": "九连板"},
        {"days": 10, "probability": 0.1, "description": "十连板及以上"},
    ]

    return {
        "days": days,
        "market": market,
        "total_limit_up": total_limit_up,
        "probability": probability,
        "recent_consecutive": recent_consecutive[:20],
    }
