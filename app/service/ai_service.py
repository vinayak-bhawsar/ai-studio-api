from __future__ import annotations

import re

from app.schemas.agent import AgentDecision
from app.service.external.llm_client import LLMClient, LLMRole


class AIService:
    """
    AI orchestration service for the creative conversation.

    The LLM decides what information is needed, what questions to ask,
    when to present creative directions, and when the user has selected
    an existing direction.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client if llm_client is not None else LLMClient()

    async def generate_response(
        self,
        *,
        conversation_history: list[dict],
        stage: str,
        creative_directions: list[dict],
    ) -> AgentDecision:
        messages = self._build_messages(
            conversation_history=conversation_history,
            stage=stage,
            creative_directions=creative_directions,
        )

        # The schema must allow an empty list for ask_question.
        # Exactly three directions are validated only for present_directions.
        schema = AgentDecision.model_json_schema()
        directions_schema = schema.get("properties", {}).get("directions")

        if isinstance(directions_schema, dict):
            directions_schema.pop("minItems", None)
            directions_schema["maxItems"] = 3

        schema["required"] = [
            "action",
            "message",
            "questions",
            "directions",
            "selected_direction_id",
        ]

        last_validation_error: Exception | None = None

        for attempt in range(2):
            request_messages = list(messages)

            if attempt == 1:
                request_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was invalid. Return one valid structured JSON decision. "
                            "If action is ask_question, you MUST provide EXACTLY ONE specific clarifying question "
                            "in the 'questions' array (max 1 item), include that question in 'message', "
                            "and set directions to an empty list. "
                            "If action is present_directions, include EXACTLY three distinct direction objects "
                            "in 'directions', each with a non-empty title and description, and set questions to []. "
                            "If the user is choosing an existing direction, use select_direction "
                            "and its exact existing ID."
                        ),
                    }
                )

            response = await self.llm_client.generate_structured(
                messages=request_messages,
                schema=schema,
                schema_name="creative_agent_decision",
                role=LLMRole.CREATIVE,
                temperature=0.1 if attempt else 0.2,
                max_tokens=8192,
            )

            try:
                candidate = AgentDecision.model_validate(response)
            except Exception as exc:
                last_validation_error = exc
                continue

            if candidate.action == "ask_question":
                valid_questions = [
                    str(q).strip() for q in candidate.questions if str(q).strip()
                ]
                if valid_questions:
                    # Enforce strictly ONE question at a time
                    single_q = valid_questions[0]
                    candidate.questions = [single_q]
                    intro = candidate.message.strip()
                    if "?" not in intro and single_q not in intro:
                        candidate.message = (
                            f"{intro}\n\n{single_q}" if intro else single_q
                        )
                else:
                    has_questions = "?" in candidate.message
                    if not has_questions:
                        last_validation_error = ValueError(
                            "Creative agent did not include a clarifying question."
                        )
                        continue

            if candidate.action == "present_directions":
                valid_directions = [
                    item
                    for item in candidate.directions
                    if str(getattr(item, "title", "") or "").strip()
                    and str(getattr(item, "description", "") or "").strip()
                ]

                if len(valid_directions) != 3:
                    last_validation_error = ValueError(
                        "Creative agent must return exactly 3 complete directions."
                    )
                    continue

                candidate.directions = valid_directions

            if (
                candidate.action == "select_direction"
                and not candidate.selected_direction_id
            ):
                last_validation_error = ValueError(
                    "Creative agent selected a direction without an ID."
                )
                continue

            return candidate

        raise RuntimeError(
            "Creative agent could not return a valid decision after retrying. "
            "Please retry your message."
        ) from last_validation_error

    async def generate_conversation_title(
        self,
        user_prompt: str,
    ) -> str:
        """
        Generate a concise, punchy title (2 to 5 words max) for a conversation based on the initial user prompt.
        """
        prompt = user_prompt.strip()
        if not prompt:
            return "Creative Idea"

        if prompt.lower() in {"hi", "hello", "hey", "start", "new", "test"}:
            return "New Project Concept"

        system_message = (
            "You are a creative titling assistant for an AI video studio. "
            "Generate a short, captivating, descriptive title (2 to 5 words maximum) for a new video project/chat "
            "based on the user's initial creative prompt or idea. "
            "Do NOT use quotation marks, markdown, punctuation, or prefixes like 'Title:'. "
            "Output ONLY the concise title."
        )

        try:
            raw_title = await self.llm_client.generate(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt[:400]},
                ],
                role=LLMRole.CREATIVE,
                temperature=0.3,
                timeout=8.0,
            )
            clean_title = raw_title.strip().strip('"\'`#*').strip()
            clean_title = re.sub(
                r"^(title|chat title|project title)[:\s]*",
                "",
                clean_title,
                flags=re.IGNORECASE,
            ).strip()
            clean_title = clean_title.split("\n")[0].strip()
            if clean_title and len(clean_title) <= 80:
                return clean_title
        except Exception:
            pass

        # Robust heuristic fallback
        words = re.sub(r"[^\w\s]", "", prompt).split()
        if words:
            candidate = " ".join(words[:4]).title()
            return candidate[:60]

        return "Creative Idea"

    @staticmethod
    def _build_messages(
        *,
        conversation_history: list[dict],
        stage: str,
        creative_directions: list[dict],
    ) -> list[dict[str, str]]:
        history_text = AIService._format_history(conversation_history)
        directions_text = AIService._format_directions(creative_directions)

        system_prompt = """
You are an award-winning Film Director, Master Screenwriter, and Veteran Video Editor collaborating with a creator in an AI video studio.
Your role is to elevate their initial concept into a gripping, visually stunning, and emotionally resonant cinematic video.

CREATIVE PROCESS & DIRECTORIAL RULES:
1. INTENT & CREATIVE GAP ANALYSIS (DO NOT BE A ROBOT):
   - Analyze the conversation history like a director and editor studying a treatment.
   - NEVER ask about details the user has already provided or strongly implied (e.g., if they mentioned a cyberpunk anime or a gritty noir thriller, NEVER ask what visual style they want; if they gave a setting or characters, NEVER re-ask for them).
   - NEVER ask a generic, robotic checklist of questions (e.g., avoid formulaic "What visual style? What tone? What audience?").
   - Instead, ask authentic, tailored questions that an original video editor and seasoned screenwriter would ask about THIS specific project.

2. PROFESSIONAL, CONTEXT-AWARE INQUIRY (action = "ask_question"):
   - When key creative pillars are missing to write the screenplay and plan the edit, ask EXACTLY ONE sharp, professional question tailored to their genre and story.
   - Draw from real cinematic and editing craft depending on what is missing:
     * Narrative Engine & Stakes: The inciting conflict, protagonist's core dilemma, or the ticking clock driving the scene.
     * Visual Language & Atmosphere: The camera movement (e.g., kinetic handheld energy vs. smooth anamorphic tracking), lighting mood (e.g., high-contrast chiaroscuro, neon haze, soft golden hour), or color palette.
     * Pacing, Rhythm & Editing Structure: How the video should cut—e.g., a fast-paced rhythmic montage matched to music beats, a slow-burn psychological tension builder, or a sudden climactic reveal.
     * Emotional Core & Climax: The emotional punch, twist, or takeaway the ending must leave the audience with.
   - In "message": Provide a concise, creative acknowledgment (1-2 sentences showing you understand their creative vision like an experienced filmmaker), followed by your single question.
   - In "questions": Include EXACTLY ONE clear question string (max 1 item).
   - Set directions to [] and selected_direction_id to null.

3. ADAPTIVE CREATIVE DIRECTIONS (action = "present_directions"):
   - Switch to "present_directions" when:
     a) The creative concept has enough clarity to pitch distinct treatments (after 1 to 2 focused questions, or immediately if the user's prompt is already detailed and clear).
     b) OR the user explicitly asks to skip questions, pitch ideas, or give options (e.g. "give me directions", "suggest 3 ideas", "skip questions", "let's go").
   - Never drag out interrogation if the vision is already solid.
   - Direction Requirements:
     - Set questions to [].
     - Return EXACTLY 3 distinct, creative directions in `directions`.
     - Each direction must feel like a compelling filmmaker's pitch:
       * Short, memorable title (2 to 4 words max).
       * Vivid description (1 to 2 sentences max) capturing the narrative hook, visual aesthetic, and editing rhythm.
     - In `message`, provide a brief, professional director's intro presenting the 3 creative routes.

4. SELECTION RULES (action = "select_direction"):
   - If active directions exist and the user selects an existing direction (by title, ordinal like "first", "second", "third", "last", or description):
     - action must be "select_direction"
     - selected_direction_id must be the exact ID of the chosen direction
     - Set questions to [] and directions to [].
     - In `message`, acknowledge their selection with excitement for writing the screenplay.

5. GREETINGS & VAGUE INPUT:
   - If the user only says "hi", "hello", or "hey", welcome them warmly and invite them to pitch their video idea or story premise.
   - Once they share an idea, analyze it like a filmmaker and ask a single tailored creative question or present directions.

CURRENT WORKFLOW STAGE:
{stage}

CURRENT CREATIVE DIRECTIONS:
{directions_text}
"""
        system_prompt = system_prompt.format(
            stage=stage,
            directions_text=directions_text,
        )

        user_context = f"""
CONVERSATION HISTORY:
{history_text}

Determine the appropriate next action:
- Evaluate the conversation history through the lens of a professional video editor and screenwriter.
- If key creative pillars (narrative engine, visual language, or editing rhythm) are genuinely missing, set action to "ask_question" and ask EXACTLY ONE tailored, professional question (in "questions" array and "message"). Do NOT repeat topics already answered.
- If the concept is already clear, or 1-2 key questions have been answered, or the user requested options/directions, set action to "present_directions" and return EXACTLY 3 distinct creative directions.
- If the user selected an existing direction, set action to "select_direction" with the matching selected_direction_id.
"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context},
        ]

    @staticmethod
    def _format_history(conversation_history: list[dict]) -> str:
        if not conversation_history:
            return "No previous conversation."

        formatted: list[str] = []

        for index, message in enumerate(conversation_history, start=1):
            role = message.get("role", "unknown")
            content = message.get("content", "")

            if not content:
                continue

            formatted.append(f"{index}. {str(role).upper()}: {content}")

        return "\n".join(formatted) if formatted else "No previous conversation."

    @staticmethod
    def _format_directions(creative_directions: list[dict]) -> str:
        if not creative_directions:
            return "No active creative directions."

        formatted: list[str] = []

        for index, direction in enumerate(creative_directions, start=1):
            direction_id = direction.get("id", "")
            title = direction.get("title", "")
            description = direction.get("description", "")

            formatted.append(
                f"{index}. id={direction_id} | title={title} | "
                f"description={description}"
            )

        return "\n".join(formatted)