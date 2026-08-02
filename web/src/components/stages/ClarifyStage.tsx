"use client";

/**
 * Step 2. The material questions, and only those.
 *
 * Each question carries why it matters and what it would change, because an executive
 * asked to answer three questions is entitled to know why these three and not thirty.
 * Required questions block execution; optional ones proceed on a disclosed default.
 */

import { useState } from "react";

import { useSession } from "@/lib/session";
import { Badge, Button, Card } from "../ui";
import { PlanningTrace } from "../panels/PlanningTrace";

export function ClarifyStage() {
  const { state, answer, reject, busy } = useSession();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const questions = state?.plan?.clarification_questions ?? [];
  const required = new Set(state?.plan?.unanswered_required_question_ids ?? []);

  const blocked = [...required].some((id) => !answers[id]?.trim());

  return (
    <div className="space-y-6">
      <Card
        title="A few things would change the analysis"
        description="Answer what you can. Anything left blank proceeds on a stated assumption, which stays visible in the plan."
      >
        <div className="space-y-5">
          {questions.map((question) => (
            <div
              key={question.question_id}
              className="rounded-lg border border-slate-200 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-medium text-slate-900">{question.question}</p>
                <Badge tone={question.required ? "warning" : "neutral"}>
                  {question.required ? "Required" : "Optional"}
                </Badge>
              </div>
              <p className="mt-1.5 text-sm text-slate-600">
                {question.why_it_matters}
              </p>
              {question.affects.length ? (
                <p className="mt-1 text-xs text-slate-500">
                  Could change: {question.affects.join(", ")}
                </p>
              ) : null}
              <input
                value={answers[question.question_id] ?? ""}
                onChange={(event) =>
                  setAnswers((current) => ({
                    ...current,
                    [question.question_id]: event.target.value,
                  }))
                }
                placeholder={
                  question.safe_default
                    ? `Leave blank to assume: ${question.safe_default}`
                    : "Your answer"
                }
                aria-label={question.question}
                className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              {question.safe_default ? (
                <p className="mt-1.5 text-xs text-slate-500">
                  Default if unanswered: {question.safe_default}
                </p>
              ) : null}
            </div>
          ))}

          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={busy || blocked}
              title={
                blocked ? "A required question is still unanswered." : undefined
              }
              onClick={() => void answer(answers)}
            >
              Submit answers
            </Button>
            <Button
              disabled={busy || required.size > 0}
              title={
                required.size > 0
                  ? "A required question cannot be skipped."
                  : undefined
              }
              onClick={() => void answer({})}
            >
              Continue without answering
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => void reject("returned to the objective")}
            >
              Change the objective
            </Button>
          </div>
        </div>
      </Card>

      <PlanningTrace />
    </div>
  );
}
