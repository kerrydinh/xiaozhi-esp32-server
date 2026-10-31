"""Gemini through its OpenAI-compatible API, with tool calls that work on Gemini 3.

Gemini 3 models attach a thought signature to each function call
(tool_calls[i].extra_content.google.thought_signature) and reject the next
request with "Function call is missing a thought_signature" when the call is
sent back without it. The server rebuilds tool calls from id, name and
arguments only, so this provider records each signature as it streams in and
puts it back on the matching tool call in the dialogue before every request.
Calls whose signature is unknown (e.g. from before a restart) get Google's
documented placeholder, which only the first call of a parallel batch needs.

Same config as the "openai" type; works for Gemini 2.5 too.
"""
from collections import OrderedDict

from config.logger import setup_logging
from core.providers.llm.openai.openai import LLMProvider as OpenAILLMProvider

TAG = __name__
logger = setup_logging()

SKIP_SIGNATURE = "skip_thought_signature_validator"
MAX_SIGNATURES = 500


def _signature_of(tool_call):
    """The thought signature on a streamed tool call delta, if any."""
    extra = getattr(tool_call, "model_extra", None) or {}
    extra_content = extra.get("extra_content") or {}
    google = extra_content.get("google") if isinstance(extra_content, dict) else None
    if isinstance(google, dict):
        return google.get("thought_signature")
    return None


class LLMProvider(OpenAILLMProvider):
    def __init__(self, config):
        super().__init__(config)
        self._signatures = OrderedDict()  # tool call id -> thought signature

    def _remember(self, call_id, signature):
        self._signatures[call_id] = signature
        self._signatures.move_to_end(call_id)
        while len(self._signatures) > MAX_SIGNATURES:
            self._signatures.popitem(last=False)

    def _attach_signatures(self, dialogue):
        for message in dialogue:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                continue
            for position, tool_call in enumerate(tool_calls):
                if not isinstance(tool_call, dict) or "extra_content" in tool_call:
                    continue
                signature = self._signatures.get(tool_call.get("id") or "")
                if signature is None and position == 0:
                    signature = SKIP_SIGNATURE
                if signature is not None:
                    tool_call["extra_content"] = {"google": {"thought_signature": signature}}

    def response(self, session_id, dialogue, **kwargs):
        self._attach_signatures(dialogue)
        yield from super().response(session_id, dialogue, **kwargs)

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        self._attach_signatures(dialogue)
        ids_by_index = {}  # a call's id arrives once; later deltas carry only its index
        for content, tool_calls in super().response_with_functions(session_id, dialogue, functions, **kwargs):
            for tool_call in tool_calls or []:
                index = getattr(tool_call, "index", None)
                if tool_call.id:
                    ids_by_index[index] = tool_call.id
                signature = _signature_of(tool_call)
                if signature:
                    self._remember(ids_by_index.get(index, tool_call.id or ""), signature)
            yield content, tool_calls
