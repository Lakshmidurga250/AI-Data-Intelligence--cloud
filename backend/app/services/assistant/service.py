"""Domain and database service layer for AI Data Intelligence Assistant."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.dataset import Dataset
from app.schemas.assistant import (
    AssistantChatResponse,
    ChatMessageCreate,
    ChatMessageRead,
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
    InsightItem,
    InsightReportResponse,
    NLQueryTranslation,
)
from app.services.assistant.engine import (
    classify_user_intent,
    discover_dataset_insights,
    generate_platform_guidance,
    translate_and_execute_nl_query,
)
from app.services.ingestion.parser import read_file_to_dataframe


async def list_conversations(
    db: AsyncSession,
    workspace_id: str,
    skip: int = 0,
    limit: int = 100,
) -> List[ConversationRead]:
    """Lists assistant conversation threads for a workspace."""
    stmt = (
        select(
            AssistantConversation,
            func.count(AssistantMessage.id).label("message_count"),
        )
        .outerjoin(AssistantMessage, AssistantConversation.id == AssistantMessage.conversation_id)
        .where(AssistantConversation.workspace_id == workspace_id)
        .group_by(AssistantConversation.id)
        .order_by(AssistantConversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    output = []
    for conv, msg_count in rows:
        output.append(
            ConversationRead(
                id=conv.id,
                workspace_id=conv.workspace_id,
                user_id=conv.user_id,
                title=conv.title,
                active_dataset_id=conv.active_dataset_id,
                message_count=msg_count,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )
    return output


async def create_conversation(
    db: AsyncSession,
    workspace_id: str,
    user_id: Optional[str],
    payload: ConversationCreate,
) -> ConversationRead:
    """Creates a new assistant conversation thread."""
    bound_dataset_id = payload.active_dataset_id or payload.dataset_id
    conv = AssistantConversation(
        workspace_id=workspace_id,
        user_id=user_id,
        title=payload.title or "New Conversation",
        active_dataset_id=bound_dataset_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    return ConversationRead(
        id=conv.id,
        workspace_id=conv.workspace_id,
        user_id=conv.user_id,
        title=conv.title,
        active_dataset_id=conv.active_dataset_id,
        message_count=0,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


async def get_conversation(
    db: AsyncSession,
    workspace_id: str,
    conversation_id: str,
) -> ConversationDetailRead:
    """Retrieves full conversation trajectory with ordered messages."""
    stmt = select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.workspace_id == workspace_id,
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant conversation not found in active workspace.",
        )

    # Fetch messages explicitly
    msg_stmt = (
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.created_at.asc())
    )
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()

    parsed_messages: List[ChatMessageRead] = []
    for m in messages:
        try:
            meta = json.loads(m.metadata_json) if m.metadata_json else {}
        except Exception:
            meta = {}
        parsed_messages.append(
            ChatMessageRead(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                intent=m.intent,
                metadata=meta,
                execution_time_ms=m.execution_time_ms,
                created_at=m.created_at,
            )
        )

    return ConversationDetailRead(
        id=conv.id,
        workspace_id=conv.workspace_id,
        user_id=conv.user_id,
        title=conv.title,
        active_dataset_id=conv.active_dataset_id,
        message_count=len(parsed_messages),
        messages=parsed_messages,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


async def delete_conversation(
    db: AsyncSession,
    workspace_id: str,
    conversation_id: str,
) -> None:
    """Deletes an assistant conversation thread."""
    stmt = select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.workspace_id == workspace_id,
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant conversation not found.",
        )

    await db.delete(conv)
    await db.commit()


async def post_chat_message(
    db: AsyncSession,
    workspace_id: str,
    user_id: Optional[str],
    conversation_id: str,
    payload: ChatMessageCreate,
) -> AssistantChatResponse:
    """Processes a user prompt, executes intelligence tools, and persists turn trajectory."""
    start_time = time.perf_counter()

    stmt = select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.workspace_id == workspace_id,
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant conversation not found.",
        )

    # Update active dataset context if provided
    incoming_ds = payload.active_dataset_id or payload.dataset_id
    target_dataset_id = incoming_ds or conv.active_dataset_id
    if incoming_ds and incoming_ds != conv.active_dataset_id:
        conv.active_dataset_id = incoming_ds

    # 1. Persist User Message
    user_msg = AssistantMessage(
        conversation_id=conv.id,
        role="user",
        content=payload.content.strip(),
        intent="user_prompt",
        metadata_json="{}",
    )
    db.add(user_msg)
    await db.flush()

    # 2. Resolve Dataset Context if available
    dataset: Optional[Dataset] = None
    df = None
    if target_dataset_id:
        ds_stmt = select(Dataset).where(
            Dataset.id == target_dataset_id,
            Dataset.workspace_id == workspace_id,
        )
        ds_res = await db.execute(ds_stmt)
        dataset = ds_res.scalar_one_or_none()
        if dataset and Path(dataset.storage_path).exists():
            try:
                df = read_file_to_dataframe(Path(dataset.storage_path), dataset.format)
            except Exception:
                df = None

    # 3. Classify intent
    intent = classify_user_intent(payload.content)
    assistant_text = ""
    discovered_insights: Optional[List[InsightItem]] = None
    nl_query_result: Optional[NLQueryTranslation] = None
    suggested_prompts: List[str] = []

    # If user asks for dataset insights or aggregations but no dataset is bound
    if (intent in ["anomaly_insights", "nl_query", "data_summary"]) and (df is None or dataset is None):
        assistant_text = (
            "I noticed you asked about tabular data or aggregations, but **no active dataset** is selected. "
            "Please bind a dataset to this conversation using the selector dropdown, or choose one of the platform guides below."
        )
        suggested_prompts = [
            "How do I upload a dataset?",
            "How do I create a Visual ETL pipeline?",
            "How to benchmark AutoML models?",
        ]
        intent = "general"

    # Execution branches
    elif intent == "anomaly_insights" and df is not None and dataset is not None:
        discovered_insights = discover_dataset_insights(df, dataset.name)
        critical_items = [i for i in discovered_insights if i.severity == "critical"]
        high_items = [i for i in discovered_insights if i.severity == "high"]
        med_items = [i for i in discovered_insights if i.severity == "medium"]

        assistant_text = (
            f"### 🔍 Automated Anomaly & Health Discovery for `{dataset.name}`\n\n"
            f"Scanned **{len(df):,}** observations and **{len(df.columns)}** features.\n\n"
            f"- **Critical Issues**: {len(critical_items)}\n"
            f"- **High Severity Risks**: {len(high_items)}\n"
            f"- **Medium Observations**: {len(med_items)}\n\n"
            "#### Key Findings:\n"
        )
        for idx, item in enumerate(discovered_insights[:5], 1):
            col_str = f" in `{item.column}`" if item.column else ""
            assistant_text += (
                f"{idx}. **[{item.severity.upper()}]** {item.title}{col_str}: {item.description}\n"
                f"   *Recommendation*: {item.recommendation}\n"
            )

        suggested_prompts = [
            f"What is the average of {df.select_dtypes(include=[np.number]).columns[0]}?"
            if len(df.select_dtypes(include=[np.number]).columns) > 0 else "Summarize dataset",
            "How do I fix missing values in Transformation Studio?",
            "Train an AutoML benchmark on this data",
        ]

    elif intent == "nl_query" and df is not None and dataset is not None:
        nl_query_result = translate_and_execute_nl_query(df, payload.content, dataset.id)
        if nl_query_result:
            assistant_text = (
                f"### 📊 Analytical Query Execution\n\n"
                f"{nl_query_result.explanation}\n\n"
                f"Found **{len(nl_query_result.data)}** aggregated records from `{dataset.name}`:\n\n"
            )
            # Markdown table summary
            if nl_query_result.columns and nl_query_result.data:
                headers = nl_query_result.columns[:4]
                assistant_text += "| " + " | ".join(headers) + " |\n"
                assistant_text += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in nl_query_result.data[:5]:
                    assistant_text += "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |\n"
                if len(nl_query_result.data) > 5:
                    assistant_text += f"\n*...and {len(nl_query_result.data) - 5} additional records.*"

            suggested_prompts = [
                "Find anomalies and outliers in this dataset",
                "Show top 5 rows with highest values",
                "How do I pin this to an Analytics Dashboard?",
            ]
        else:
            assistant_text = (
                f"I parsed your query against `{dataset.name}`, but could not extract a clear aggregation or filter. "
                "Try asking for a specific metric (e.g. *'average balance by churn'*, *'sum amount'*, *'top 10 rows'*)."
            )
            suggested_prompts = ["Summarize dataset", "Find anomalies and outliers", "List column types"]

    elif intent == "data_summary" and df is not None and dataset is not None:
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
        total_cells = len(df) * len(df.columns)
        null_cells = int(df.isnull().sum().sum())
        completeness = round(100.0 - (null_cells / max(total_cells, 1) * 100.0), 2)

        assistant_text = (
            f"### 📋 Dataset Overview: `{dataset.name}`\n\n"
            f"- **Total Records**: {len(df):,} rows\n"
            f"- **Feature Columns**: {len(df.columns)} ({len(num_cols)} numerical, {len(cat_cols)} categorical)\n"
            f"- **Data Completeness**: {completeness}%\n"
            f"- **Storage Format**: `{dataset.format.upper()}`\n\n"
            f"**Numerical Features**: {', '.join(num_cols[:6]) or 'None'}\n\n"
            f"**Categorical Features**: {', '.join(cat_cols[:6]) or 'None'}\n"
        )
        suggested_prompts = [
            "Find anomalies and outliers in this dataset",
            f"What is the average {num_cols[0]}?" if num_cols else "Show top 5 rows",
            "How do I build an ETL pipeline with this dataset?",
        ]

    elif intent == "navigation":
        assistant_text = generate_platform_guidance(payload.content)
        suggested_prompts = [
            "How to benchmark AutoML models?",
            "How do I create a Visual ETL pipeline?",
            "Where do I set up Celery schedules?",
            "How do I add BI dashboard widgets?",
        ]

    else:
        assistant_text = generate_platform_guidance(payload.content)
        suggested_prompts = [
            "Find anomalies and outliers in this dataset",
            "Summarize active dataset",
            "How do I create a Visual ETL pipeline?",
        ]

    exec_time = round((time.perf_counter() - start_time) * 1000, 2)

    # 4. Save Assistant Turn
    metadata_obj: Dict[str, Any] = {
        "intent": intent,
        "execution_time_ms": exec_time,
        "suggested_prompts": suggested_prompts,
    }
    if discovered_insights:
        metadata_obj["insights"] = [i.model_dump() for i in discovered_insights]
    if nl_query_result:
        metadata_obj["query_result"] = nl_query_result.model_dump()

    assistant_msg = AssistantMessage(
        conversation_id=conv.id,
        role="assistant",
        content=assistant_text,
        intent=intent,
        metadata_json=json.dumps(metadata_obj),
        execution_time_ms=exec_time,
    )
    db.add(assistant_msg)

    # Auto-generate dynamic title from first user query if still default
    if conv.title == "New Conversation":
        snippet = payload.content.strip().split("\n")[0][:40]
        conv.title = snippet.capitalize()

    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return AssistantChatResponse(
        conversation_id=conv.id,
        user_message=ChatMessageRead(
            id=user_msg.id,
            conversation_id=user_msg.conversation_id,
            role=user_msg.role,
            content=user_msg.content,
            intent=user_msg.intent,
            metadata={},
            created_at=user_msg.created_at,
        ),
        assistant_message=ChatMessageRead(
            id=assistant_msg.id,
            conversation_id=assistant_msg.conversation_id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            intent=assistant_msg.intent,
            metadata=metadata_obj,
            execution_time_ms=assistant_msg.execution_time_ms,
            created_at=assistant_msg.created_at,
        ),
        intent=intent,
        insights=discovered_insights,
        query_result=nl_query_result,
        suggested_prompts=suggested_prompts,
    )


async def generate_dataset_insights(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
) -> InsightReportResponse:
    """Direct on-demand execution of automated anomaly and trend discovery."""
    ds_stmt = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    ds_res = await db.execute(ds_stmt)
    dataset = ds_res.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found in workspace.",
        )

    file_path = Path(dataset.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found on disk.",
        )

    df = read_file_to_dataframe(file_path, dataset.format)
    insights = discover_dataset_insights(df, dataset.name)
    critical_count = sum(1 for i in insights if i.severity == "critical")

    return InsightReportResponse(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        total_rows=len(df),
        total_columns=len(df.columns),
        total_insights=len(insights),
        critical_count=critical_count,
        insights=insights,
        generated_at=datetime.now(timezone.utc),
    )
