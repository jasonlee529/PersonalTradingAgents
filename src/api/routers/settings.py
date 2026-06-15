import os
import sys
from pathlib import Path

# Ensure src/agents/ is on sys.path for tradingagents imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_services, AppServices
from src.api.models import (
    SettingsResponse,
    SettingsUpdate,
    AnalystsResponse,
    AnalystInfo,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
    RunTaskResponse,
    LLMProvidersResponse,
    LLMProviderInfo,
    LLMProviderSettings,
)
from src.agents.tradingagents.agents.analyst_registry import AnalystRegistry
from src.config import PERSISTED_SETTINGS_FIELDS, persist_env_file_values

router = APIRouter(prefix="/settings", tags=["settings"])

# Field → .env var name mapping (only fields that should be persisted)
_PERSISTED_FIELDS: dict[str, str] = {
    "daily_direction_llm_provider": "DAILY_DIRECTION_LLM_PROVIDER",
    "wiki_llm_provider": "WIKI_LLM_PROVIDER",
    "openai_api_key": "OPENAI_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
    "xai_api_key": "XAI_API_KEY",
    "dashscope_api_key": "DASHSCOPE_API_KEY",
    "dashscope_cn_api_key": "DASHSCOPE_CN_API_KEY",
    "zhipu_api_key": "ZHIPU_API_KEY",
    "zhipu_cn_api_key": "ZHIPU_CN_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
    "minimax_cn_api_key": "MINIMAX_CN_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "kimi_api_key": "KIMI_API_KEY",
    "scheduler_enabled": "SCHEDULER_ENABLED",
    "analysis_schedule": "ANALYSIS_SCHEDULE",
    "daily_direction_notification_enabled": "DAILY_DIRECTION_NOTIFICATION_ENABLED",
    "notification_report_channels": "NOTIFICATION_REPORT_CHANNELS",
    "wechat_webhook_url": "WECHAT_WEBHOOK_URL",
    "wechat_msg_type": "WECHAT_MSG_TYPE",
    "wechat_max_bytes": "WECHAT_MAX_BYTES",
    "feishu_webhook_url": "FEISHU_WEBHOOK_URL",
    "feishu_webhook_secret": "FEISHU_WEBHOOK_SECRET",
    "feishu_webhook_keyword": "FEISHU_WEBHOOK_KEYWORD",
    "feishu_max_bytes": "FEISHU_MAX_BYTES",
    "email_sender": "EMAIL_SENDER",
    "email_password": "EMAIL_PASSWORD",
    "email_receivers": "EMAIL_RECEIVERS",
    "email_sender_name": "EMAIL_SENDER_NAME",
    "webhook_verify_ssl": "WEBHOOK_VERIFY_SSL",
    "test_mode": "TEST_MODE",
    "trade_commission_rate": "TRADE_COMMISSION_RATE",
    "trade_min_commission": "TRADE_MIN_COMMISSION",
    "trade_stamp_tax_rate": "TRADE_STAMP_TAX_RATE",
    "trade_transfer_fee_rate": "TRADE_TRANSFER_FEE_RATE",
}
_PERSISTED_FIELDS = PERSISTED_SETTINGS_FIELDS
_LLM_RUNTIME_FIELDS = {
    "daily_direction_llm_provider",
    "wiki_llm_provider",
    "llm_provider_configs",
    "openai_api_key",
    "deepseek_api_key",
    "anthropic_api_key",
    "google_api_key",
    "azure_openai_api_key",
    "xai_api_key",
    "dashscope_api_key",
    "dashscope_cn_api_key",
    "zhipu_api_key",
    "zhipu_cn_api_key",
    "minimax_api_key",
    "minimax_cn_api_key",
    "openrouter_api_key",
    "kimi_api_key",
    "test_mode",
}


def _provider_catalog_helpers():
    from src.agents.tradingagents.llm_clients.provider_catalog import (
        get_all_providers,
        get_api_key_field,
        get_model_settings_field,
    )

    return get_all_providers, get_api_key_field, get_model_settings_field


def _provider_config_fields(provider_id: str) -> tuple[str, str, str]:
    _, get_api_key_field, get_model_settings_field = _provider_catalog_helpers()
    return (
        get_model_settings_field(provider_id, "quick"),
        get_model_settings_field(provider_id, "deep"),
        get_api_key_field(provider_id),
    )


def _persist_settings_to_env(s, fields: set[str] | None = None) -> None:
    """Write current settings back to the .env file so they survive restarts."""
    env_path = Path(getattr(s, "settings_env_path", ".env"))
    if not env_path.is_absolute():
        env_path = Path(__file__).resolve().parents[3] / env_path
    updates: dict[str, object] = {}
    for field, env_var in _PERSISTED_FIELDS.items():
        if fields is not None and field not in fields:
            continue
        value = getattr(s, field, None)
        if value is None:
            continue
        updates[env_var] = value
    persist_env_file_values(env_path, updates)


def _sync_settings_to_process_env(s, fields: set[str] | None = None) -> None:
    """Make settings changes visible to code that reads os.environ directly."""
    for field, env_var in _PERSISTED_FIELDS.items():
        if fields is not None and field not in fields:
            continue
        value = getattr(s, field, None)
        if value is None:
            continue
        os.environ[env_var] = "true" if value is True else "false" if value is False else str(value)


def _settings_to_response(s) -> SettingsResponse:
    get_all_providers, _, _ = _provider_catalog_helpers()
    provider_configs = {}
    for provider in get_all_providers():
        quick_field, deep_field, key_field = _provider_config_fields(provider.id)
        provider_configs[provider.id] = LLMProviderSettings(
            quick_model=getattr(s, quick_field, "") or provider.default_quick_model,
            deep_model=getattr(s, deep_field, "") or provider.default_deep_model,
            api_key=getattr(s, key_field, "") if key_field else "",
        )

    return SettingsResponse(
        daily_direction_llm_provider=s.daily_direction_llm_provider,
        wiki_llm_provider=s.wiki_llm_provider,
        llm_provider_configs=provider_configs,
        openai_api_key=s.openai_api_key,
        deepseek_api_key=s.deepseek_api_key,
        anthropic_api_key=s.anthropic_api_key,
        google_api_key=s.google_api_key,
        azure_openai_api_key=s.azure_openai_api_key,
        xai_api_key=s.xai_api_key,
        dashscope_api_key=s.dashscope_api_key,
        dashscope_cn_api_key=s.dashscope_cn_api_key,
        zhipu_api_key=s.zhipu_api_key,
        zhipu_cn_api_key=s.zhipu_cn_api_key,
        minimax_api_key=s.minimax_api_key,
        minimax_cn_api_key=s.minimax_cn_api_key,
        openrouter_api_key=s.openrouter_api_key,
        kimi_api_key=s.kimi_api_key,
        scheduler_enabled=s.scheduler_enabled,
        analysis_schedule=s.analysis_schedule,
        daily_direction_notification_enabled=s.daily_direction_notification_enabled,
        notification_report_channels=s.notification_report_channels,
        wechat_webhook_url=s.wechat_webhook_url,
        wechat_msg_type=s.wechat_msg_type,
        wechat_max_bytes=s.wechat_max_bytes,
        feishu_webhook_url=s.feishu_webhook_url,
        feishu_webhook_secret=s.feishu_webhook_secret,
        feishu_webhook_keyword=s.feishu_webhook_keyword,
        feishu_max_bytes=s.feishu_max_bytes,
        email_sender=s.email_sender,
        email_password=s.email_password,
        email_receivers=s.email_receivers,
        email_sender_name=s.email_sender_name,
        webhook_verify_ssl=s.webhook_verify_ssl,
        test_mode=s.test_mode,
        trade_commission_rate=s.trade_commission_rate,
        trade_min_commission=s.trade_min_commission,
        trade_stamp_tax_rate=s.trade_stamp_tax_rate,
        trade_transfer_fee_rate=s.trade_transfer_fee_rate,
        xueqiu_cookie=s.xueqiu_cookie,
        xueqiu_auto_cookie=s.xueqiu_auto_cookie,
        xueqiu_timeout=s.xueqiu_timeout,
        tushare_api_key=s.tushare_api_key,
        fund_holdings_refresh_enabled=s.fund_holdings_refresh_enabled,
        fund_holdings_refresh_schedule=s.fund_holdings_refresh_schedule,
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(services: AppServices = Depends(get_services)):
    return _settings_to_response(services.settings)


@router.patch("", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdate, services: AppServices = Depends(get_services)):
    s = services.settings
    scheduler_enabled_before = getattr(s, "scheduler_enabled", False)
    changes = body.model_dump(exclude_unset=True)
    provider_config_changes = changes.pop("llm_provider_configs", None)
    empty_string_fields = {"daily_direction_llm_provider", "wiki_llm_provider"}
    for field, value in changes.items():
        if field in empty_string_fields and value is None:
            value = ""
        if hasattr(s, field):
            setattr(s, field, value)
    changed_fields = set(changes)
    if provider_config_changes:
        for provider_id, provider_values in provider_config_changes.items():
            quick_field, deep_field, key_field = _provider_config_fields(provider_id)
            if provider_values.get("quick_model") is not None and hasattr(s, quick_field):
                setattr(s, quick_field, provider_values["quick_model"])
                changed_fields.add(quick_field)
            if provider_values.get("deep_model") is not None and hasattr(s, deep_field):
                setattr(s, deep_field, provider_values["deep_model"])
                changed_fields.add(deep_field)
            if key_field and provider_values.get("api_key") is not None and hasattr(s, key_field):
                setattr(s, key_field, provider_values["api_key"])
                changed_fields.add(key_field)
        changed_fields.add("llm_provider_configs")
    _persist_settings_to_env(s, changed_fields)
    _sync_settings_to_process_env(s, changed_fields)
    scheduler_enabled_after = getattr(s, "scheduler_enabled", False)
    if scheduler_enabled_after != scheduler_enabled_before:
        if scheduler_enabled_after:
            services.scheduler.start()
        else:
            services.scheduler.stop()
    if changed_fields & _LLM_RUNTIME_FIELDS:
        services.restart_job_worker()
    return _settings_to_response(s)


@router.get("/analysts", response_model=AnalystsResponse)
async def get_analysts():
    reg = AnalystRegistry()
    return AnalystsResponse(
        analysts=[AnalystInfo(**e.to_dict()) for e in reg.list()],
        defaults=reg.default_names(),
    )


@router.get("/tasks", response_model=list[ScheduledTaskResponse])
async def list_tasks(services: AppServices = Depends(get_services)):
    return services.scheduler.list_tasks()


@router.patch("/tasks/{task_id}", response_model=ScheduledTaskResponse)
async def update_task(
    task_id: str,
    body: ScheduledTaskUpdate,
    services: AppServices = Depends(get_services),
):
    tasks = {t["id"]: t for t in services.scheduler.list_tasks()}
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    await services.scheduler.update_task(
        task_id, enabled=body.enabled, cron=body.cron
    )
    tasks = {t["id"]: t for t in services.scheduler.list_tasks()}
    return ScheduledTaskResponse(**tasks[task_id])


@router.post("/tasks/{task_id}/run", response_model=RunTaskResponse)
async def run_task_now(
    task_id: str,
    services: AppServices = Depends(get_services),
):
    result = await services.scheduler.run_task_now(task_id)
    return RunTaskResponse(
        task_id=task_id,
        success=result.get("success", False),
        message=result.get("message", ""),
    )


@router.get("/llm-providers", response_model=LLMProvidersResponse)
async def get_llm_providers():
    import sys
    from pathlib import Path

    _agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
    if str(_agents_dir) not in sys.path:
        sys.path.insert(0, str(_agents_dir))

    from tradingagents.llm_clients.provider_catalog import get_all_providers

    providers = get_all_providers()
    return LLMProvidersResponse(
        providers=[LLMProviderInfo(**p.to_dict()) for p in providers]
    )
