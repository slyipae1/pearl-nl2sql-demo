"""Specification Questions Panel: Full HTML + Custom JS Implementation

This module generates a unified HTML form for displaying and collecting answers to
specification questions. All questions appear simultaneously, eliminating the need
for Gradio selector/checkbox/textbox controls.

Exports:
- generate_specifying_questions_form_html(questions: list[dict]) -> str
- generate_spec_questions_js_control() -> str
"""

import html
from typing import Any


def generate_specifying_questions_form_html(questions: list[dict[str, Any]]) -> str:
    """Generate HTML form displaying all pending specification questions as interactive cards.
    
    Args:
        questions: List of question dicts with keys:
            - question_id: unique question identifier
            - question: question text
            - choices: list of answer choices
            - preselect_option_idxs: list of indices to visually highlight as suggested
            - hidden_rationale: context/evidence text (hidden by default)
            - manager_rationale: manager's note on why question was asked
            - evaluator_justification: evaluation evidence
            - answer: dict with current answer (multi_choices[], free_text)
    
    Returns:
        Complete HTML string with all question cards, embedded styles, and form structure.
        Does NOT include the controlling JavaScript; call generate_spec_questions_js_control() separately.
    """
    if not questions:
        return ""
    
    cards_html = []
    for question in questions:
        card_html = _render_question_card(question)
        if card_html:
            cards_html.append(card_html)
    
    if not cards_html:
        return ""
    
    form_html = (
      '<div id="spec-questions-form" class="spec-questions-wrapper">'
      '<div class="spec-questions-toolbar">'
      '  <button class="spec-submit-btn" id="spec-submit-btn" type="button">Submit Clarifications</button>'
      '</div>'
      '<div class="spec-questions-container">'
      + "".join(cards_html)
      + '</div>'
      '</div>'
    )
    
    return form_html


def _render_question_card(question: dict[str, Any]) -> str:
    """Render a single question as an interactive form card.
    
    Returns HTML for one question card including:
    - Header with Q ID
    - Question text
    - Interactive checkboxes for choices (with preselection hints)
    - Free-text input area
    - Collapsible evidence section
    """
    qid = html.escape(str(question.get("question_id") or ""))
    qtext = html.escape(str(question.get("question") or "").strip())
    choices = question.get("choices") or []
    preselect_idxs = {int(idx) for idx in (question.get("preselect_option_idxs") or []) if str(idx).strip().isdigit()}
    
    if not qid or not qtext:
        return ""
    
    # Render choices as checkboxes
    choices_html = _render_choices_section(qid, choices, preselect_idxs)
    
    # Render evidence section
    evidence_html = _render_evidence_section(question)
    
    # Render free-text area
    free_text_value = ""
    current_answer = question.get("answer") or {}
    if isinstance(current_answer, dict):
        free_text_value = html.escape(str(current_answer.get("free_text") or ""))    
    card_html = (
      f'<div class="spec-q-card" data-question-id="{html.escape(qid)}">'
      f'<div class="spec-q-header">'
      f'  <strong class="spec-q-id">{html.escape(qid)}</strong>'
      f'  <span class="spec-q-status"></span>'
      f'</div>'
      f'<div class="spec-q-text">{qtext}</div>'
      + choices_html +
      f'<div class="spec-q-freetext">'
      f'  <textarea class="spec-q-textarea" placeholder="Additional notes or clarification..." rows="2">{free_text_value}</textarea>'
      f'</div>'
      + evidence_html +
      f'</div>'
    )
    
    return card_html


def _render_choices_section(qid: str, choices: list[str], preselect_idxs: set[int]) -> str:
    """Render interactive checkboxes for multiple-choice answers.
    
    Preselected options show with:
    - Green background (#d4f1d4) with "Suggested" badge
    - Unchecked by default (user must explicitly select)
    - Opacity styling to differentiate from other choices
    """
    if not choices:
        return ""
    
    choice_items = []
    for idx, choice_text in enumerate(choices):
        choice_text = str(choice_text or "").strip()
        if not choice_text:
            continue
        
        choice_escaped = html.escape(choice_text)
        is_preselected = idx in preselect_idxs
        
        # Visual styling for preselected items
        if is_preselected:
            class_name = "choice-item preselect-hint"
            badge_html = '<span class="preselect-badge">suggested</span>'
        else:
            class_name = "choice-item"
            badge_html = ""
        
        choice_items.append(
            f'<label class="{class_name}" data-choice-idx="{idx}" data-preselect="{str(is_preselected).lower()}">'
            f'  <input type="checkbox" class="choice-checkbox" />'
            f'  <code class="choice-code">{choice_escaped}</code>'
            f'  {badge_html}'
            f'</label>'
        )
    
    if not choice_items:
        return ""
    
    return (
        '<div class="spec-q-choices">'
        + ''.join(choice_items)
        + '</div>'
    )


def _render_evidence_section(question: dict[str, Any]) -> str:
    """Render collapsible evidence section with manager note only.
    
    Uses HTML <details> element for collapsible content.
    """
    evidence_parts = []
    
    if question.get("manager_rationale"):
        evidence_parts.append(
            f'<div class="evidence-item">'
            f'  <strong>Manager Note:</strong> {html.escape(str(question.get("manager_rationale")))}'
            f'</div>'
        )
    
    if not evidence_parts:
        return ""
    
    return (
    '<details class="spec-q-evidence">'
    '  <summary class="evidence-summary">Manager Note</summary>'
        '  <div class="evidence-content">'
        + ''.join(evidence_parts)
        + '</div>'
        '</details>'
    )


SPEC_QUESTIONS_JS_CODE = """
(function() {
  "use strict";
  
  if (window.__SpecQuestionsControlBound) return;
  window.__SpecQuestionsControlBound = true;
  
  // Utility: safely get element by ID
  function qs(id) {
    return document.getElementById(id);
  }
  
  // Utility: get all elements by selector (optionally scoped)
  function qsa(selector, root) {
    const scope = root || document;
    return Array.from(scope.querySelectorAll(selector) || []);
  }
  
  // Find a Gradio input element using elem_id wrapper first, then fallbacks.
  function findGradioInput(partialId) {
    console.log("[findGradioInput] Looking for field:", partialId);
    
    // Preferred path: elem_id is on wrapper, input/textarea is inside.
    const wrapper = qs(partialId);
    console.log("[findGradioInput] Wrapper found:", wrapper);
    
    if (wrapper) {
      const inner = wrapper.querySelector("textarea, input");
      if (inner) {
        console.log("[findGradioInput] Found inner", inner.tagName, "inside wrapper");
        return inner;
      }
      console.log("[findGradioInput] Wrapper found but no textarea/input inside");
      // Try data-testid path (Gradio may use this)
      const byTestId = wrapper.querySelector('[data-testid*="' + partialId + '"]');
      if (byTestId) {
        console.log("[findGradioInput] Found via data-testid");
        return byTestId;
      }
    }

    // Fallback: search by id pattern
    const elements = qsa('textarea[id*="' + partialId + '"], input[id*="' + partialId + '"]');
    if (elements.length > 0) {
      console.log("[findGradioInput] Found via id pattern:", elements[0].id);
      return elements[0];
    }
    
    // Try to find by aria-label
    const ariaLabel = qsa('[aria-label*="' + partialId + '"]');
    if (ariaLabel.length > 0) {
      console.log("[findGradioInput] Found via aria-label");
      return ariaLabel[0];
    }
    
    // Try exact ID match
    const exact = qs(partialId);
    if (exact && (exact.tagName === 'TEXTAREA' || exact.tagName === 'INPUT')) {
      console.log("[findGradioInput] Found via exact ID:", exact.tagName);
      return exact;
    }
    
    console.error("[findGradioInput] FAILED to find input for:", partialId);
    return null;
  }
  
  // Collect form data from a single question card
  function collectQuestionAnswer(cardDiv) {
    const qid = cardDiv.getAttribute("data-question-id");
    if (!qid) return null;
    
    // Collect checked choices
    const checkedChoices = [];
    qsa('input[type="checkbox"]', cardDiv).forEach(checkbox => {
      if (checkbox.checked) {
        const label = checkbox.parentElement;
        const codeEl = label.querySelector("code");
        if (codeEl) {
          checkedChoices.push(codeEl.textContent);
        }
      }
    });
    
    // Collect free-text
    const textarea = cardDiv.querySelector("textarea");
    const freeText = textarea ? (textarea.value || "").trim() : "";
    
    return {
      question_id: qid,
      multi_choices: checkedChoices,
      free_text: freeText
    };
  }

  // Collect all question answers from the current HTML form
  function collectAllQuestionAnswers() {
    const cards = qsa(".spec-q-card", qs("spec-questions-form"));
    const items = [];
    cards.forEach(card => {
      const answer = collectQuestionAnswer(card);
      if (!answer) return;
      answer.is_answered = Boolean((answer.multi_choices || []).length || (answer.free_text || "").trim());
      items.push(answer);
    });
    console.log("[collectAllQuestionAnswers] Collected items:", items);
    return items;
  }
  
  // Update hidden Gradio input fields with collected data
  function updateHiddenGradioFields(formData) {
    console.log("[updateHiddenGradioFields] Collecting submission data:", formData);
    
    // Find hidden Gradio input elements
    const hiddenSubmissionInput = findGradioInput("spec_hidden_submission");
    
    console.log("[updateHiddenGradioFields] Found input:", {
      submission: !!hiddenSubmissionInput
    });
    
    if (!hiddenSubmissionInput) {
      console.error("[updateHiddenGradioFields] FAILED - Could not find hidden submission field");
      return false;
    }
    
    // Set values
    try {
      const submissionValue = JSON.stringify(formData || []);
      console.log("[updateHiddenGradioFields] Setting submission value:", submissionValue);
      hiddenSubmissionInput.value = submissionValue;
      hiddenSubmissionInput.dispatchEvent(new Event("input", { bubbles: true }));
      
      console.log("[updateHiddenGradioFields] Successfully updated and dispatched events");
      return true;
    } catch (e) {
      console.error("[updateHiddenGradioFields] Failed to update hidden fields: ", e);
      return false;
    }
  }
  
  function findGradioButton(buttonId) {
    console.log("[findGradioButton] Looking for button:", buttonId);
    
    const wrapper = qs(buttonId);
    if (wrapper) {
      const innerBtn = wrapper.querySelector("button");
      if (innerBtn) {
        console.log("[findGradioButton] Found button inside wrapper");
        return innerBtn;
      }
      console.log("[findGradioButton] Wrapper found but no button inside");
    }
    
    const btn = qs(buttonId);
    if (btn && btn.tagName === "BUTTON") {
      console.log("[findGradioButton] Found button via exact ID");
      return btn;
    }
    
    console.error("[findGradioButton] FAILED to find button:", buttonId);
    return null;
  }

  // Trigger hidden Gradio button with collected data
  function triggerGradioButton(buttonId, formData) {
    console.log("[triggerGradioButton] Starting for button:", buttonId);
    
    const btn = findGradioButton(buttonId);
    if (!btn) {
      console.error("[triggerGradioButton] Button not found: " + buttonId);
      return false;
    }
    
    // Update hidden fields first
    if (!updateHiddenGradioFields(formData)) {
      console.error("[triggerGradioButton] Failed to update hidden fields");
      return false;
    }
    
    // Trigger click event
    try {
      console.log("[triggerGradioButton] Clicking button:", btn);
      btn.click();
      console.log("[triggerGradioButton] Button clicked successfully");
      return true;
    } catch (e) {
      console.error("[triggerGradioButton] Failed to trigger button click: ", e);
      return false;
    }
  }
  
  // Handle Submit button click for the whole clarification form
  function handleSubmitQuestions(evt) {
    console.log("[handleSubmitQuestions] Submit clicked");
    evt.preventDefault();
    const btn = evt.target;
    const allAnswers = collectAllQuestionAnswers();
    const answered = allAnswers.filter(item => item.is_answered).length;
    const skipped = allAnswers.length - answered;
    console.log("[handleSubmitQuestions] Answer summary:", { total: allAnswers.length, answered, skipped });
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = "Submitting...";
    
    // Trigger hidden Gradio button
    const success = triggerGradioButton("spec_submit_btn", allAnswers);
    
    if (!success) {
      console.error("[handleSubmitQuestions] Failed to trigger Gradio button");
      btn.disabled = false;
      btn.textContent = originalText;
    } else {
      console.log("[handleSubmitQuestions] Successfully triggered submit");
    }
  }
  
  // Bind delegated click listener once; survives HTML rerenders.
  function bindEventListeners() {
    console.log("[bindEventListeners] Binding delegated click listener");
    document.addEventListener("click", function(evt) {
      const submitBtn = evt.target.closest(".spec-submit-btn");
      if (submitBtn) {
        console.log("[bindEventListeners] Submit button event detected");
        handleSubmitQuestions({ preventDefault: () => evt.preventDefault(), target: submitBtn });
        return;
      }
    });
  }
  
  // Initialize on page ready
  function init() {
    console.log("[init] Initializing spec questions control");
    bindEventListeners();
    console.log("[init] Initialization complete");
  }
  
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""


def generate_spec_questions_js_control() -> str:
    """Generate self-contained JavaScript module for spec-questions form control.

    Returns:
        Complete <script> tag with all JS code embedded.
    """
    return f"<script>\n{SPEC_QUESTIONS_JS_CODE}\n</script>"


# CSS Styles for spec-questions form
CSS_SPEC_QUESTIONS = """
#spec-questions-form {
  width: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.spec-questions-wrapper {
  padding: 12px 0;
}

.spec-questions-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.spec-submit-btn {
  border: 1px solid #6f93c7;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  color: #ffffff;
  background: linear-gradient(180deg, #4f7dbd 0%, #3567ac 100%);
  box-shadow: 0 1px 3px rgba(53, 103, 172, 0.18);
}

.spec-submit-btn:hover:not(:disabled) {
  background: linear-gradient(180deg, #5a89c6 0%, #3c70b7 100%);
}

.spec-submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spec-questions-container {
  display: grid;
  gap: 12px;
  max-height: 600px;
  overflow-y: auto;
}

.spec-q-card {
  border: 1px solid #d6dfec;
  border-radius: 8px;
  padding: 12px;
  background: #fbfdff;
  transition: box-shadow 200ms ease;
}

.spec-q-card:hover {
  box-shadow: 0 2px 8px rgba(109, 127, 161, 0.15);
}

.spec-q-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.spec-q-id {
  font-weight: 700;
  color: #1d3f6e;
  font-size: 14px;
}

.spec-q-status {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  background: transparent;
}

.spec-q-status.saving {
  background: #e3f2fd;
  color: #1976d2;
}

.spec-q-status.skipping {
  background: #fff3e0;
  color: #f57c00;
}

.spec-q-status.error {
  background: #ffebee;
  color: #c62828;
}

.spec-q-text {
  margin-bottom: 10px;
  font-size: 14px;
  color: #2d3a54;
  line-height: 1.4;
}

.spec-q-choices {
  margin: 10px 0;
  display: grid;
  gap: 6px;
}

.choice-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #f8fbff;
  cursor: pointer;
  transition: all 150ms ease;
}

.choice-item:hover {
  border-color: #a8c5e2;
  background: #f4f9ff;
}

.choice-item.preselect-hint {
  background: #e8f5e8;
  border-color: #a5d6a7;
}

.choice-item.preselect-hint:hover {
  background: #dff0d8;
  border-color: #7fb57f;
}

.choice-checkbox {
  margin-top: 3px;
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.choice-code {
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  font-size: 13px;
  color: #1d3f6e;
  background: transparent;
  padding: 0;
}

.preselect-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: #2e7d32;
  background: #c8e6c9;
  padding: 2px 6px;
  border-radius: 3px;
}

.spec-q-freetext {
  margin: 10px 0;
}

.spec-q-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #dbe3ef;
  border-radius: 4px;
  font-family: inherit;
  font-size: 13px;
  resize: vertical;
  color: #2d3a54;
}

.spec-q-textarea:focus {
  outline: none;
  border-color: #7fa5d9;
  box-shadow: 0 0 0 2px rgba(127, 165, 217, 0.1);
}

.spec-q-evidence {
  margin: 10px 0;
  padding: 10px;
  border-top: 1px dashed #d6dfec;
  border-left: 3px solid #7fa5d9;
  background: #f0f4fb;
  border-radius: 4px;
}

.spec-q-evidence[open] {
  background: #f5f9ff;
}

.evidence-summary {
  cursor: pointer;
  font-weight: 600;
  color: #1d3f6e;
  font-size: 13px;
  user-select: none;
  padding: 4px 0;
}

.evidence-summary:hover {
  color: #2d5aa8;
}

.evidence-content {
  margin-top: 8px;
  display: grid;
  gap: 8px;
  font-size: 12px;
  color: #546680;
  line-height: 1.4;
}

.evidence-item {
  padding: 6px;
  background: #ffffff;
  border-left: 2px solid #a8c5e2;
  border-radius: 3px;
}

.evidence-item strong {
  color: #2d3a54;
}

.spec-q-buttons {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.spec-save-btn,
.spec-skip-btn {
  padding: 7px 12px;
  border: 1px solid #bfd0e6;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms ease;
  background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%);
  color: #1d3f6e;
}

.spec-save-btn:hover:not(:disabled) {
  border-color: #7fa5d9;
  background: linear-gradient(180deg, #ffffff 0%, #eaf2ff 100%);
  box-shadow: 0 2px 6px rgba(127, 165, 217, 0.2);
}

.spec-skip-btn:hover:not(:disabled) {
  border-color: #d68910;
  color: #d68910;
}

.spec-save-btn:disabled,
.spec-skip-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
"""
