import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ChatResponse } from "../api/types";
import { Card } from "../components/ui";
import { track } from "../lib/analytics";

const EXAMPLES = [
  "Which programs collaborate most with Cancer Prevention & Control?",
  "Top 10 most-cited publications since 2020 and their journals.",
  "How has inter-programmatic collaboration changed over the last decade?",
  "What share of our publications are open access by program?",
];

interface Turn {
  question: string;
  response?: ChatResponse;
}

interface HistoryTurn {
  role: "user" | "model";
  text: string;
}

// Carry the conversation so follow-ups have context: each prior turn becomes a
// user message + a model message containing the answer AND the SQL it ran, so
// the model can build on previous queries ("show that by program", "what about
// 2022?"). The last ~10 turns are sent to keep the payload bounded.
function buildHistory(turns: Turn[]): HistoryTurn[] {
  const history: HistoryTurn[] = [];
  for (const t of turns.slice(-10)) {
    if (!t.response || t.response.error) continue;
    history.push({ role: "user", text: t.question });
    const sql = t.response.queries.length
      ? `\n\nSQL I ran:\n${t.response.queries.join(";\n")}`
      : "";
    history.push({ role: "model", text: `${t.response.answer}${sql}` });
  }
  return history;
}

export function Ask() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");

  const ask = useMutation({
    mutationFn: ({ q, history }: { q: string; history: HistoryTurn[] }) => api.chat(q, history),
    onSuccess: (response, { q }) =>
      setTurns((t) =>
        t.map((turn) => (turn.question === q && !turn.response ? { ...turn, response } : turn)),
      ),
  });

  const submit = (q: string, source: string = "input") => {
    if (!q.trim()) return;
    track("ask_question", { source, turn: turns.length + 1 });
    const history = buildHistory(turns);
    setTurns((t) => [...t, { question: q }]);
    setInput("");
    ask.mutate({ q, history });
  };

  return (
    <div className="ask">
      <h1>Ask the Data</h1>
      <p className="lede">
        Plain-English questions, answered by querying the cancer-center tables live — every number
        is backed by a SQL query you can inspect.
      </p>

      {turns.length === 0 && (
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => submit(ex, "example")}>
              {ex}
            </button>
          ))}
        </div>
      )}

      <div className="chat-log">
        {turns.map((t, i) => (
          <div key={i} className="turn">
            <div className="msg user">{t.question}</div>
            {t.response ? (
              <Answer
                response={t.response}
                onPick={(q) => submit(q, "suggestion")}
                showSuggestions={i === turns.length - 1 && !ask.isPending}
              />
            ) : (
              <div className="msg assistant muted">Querying…</div>
            )}
          </div>
        ))}
        {ask.isError && <div className="error">Request failed: {String(ask.error)}</div>}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <input
          placeholder="Ask about publications, programs, members, impact…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={ask.isPending}>
          Ask
        </button>
      </form>
    </div>
  );
}

function Answer({
  response,
  onPick,
  showSuggestions,
}: {
  response: ChatResponse;
  onPick: (q: string) => void;
  showSuggestions: boolean;
}) {
  if (response.error) return <div className="msg assistant error">{response.error}</div>;
  const table = response.table ?? [];
  const cols = table.length ? Object.keys(table[0]) : [];
  return (
    <div className="msg assistant">
      <div className="answer-text">{response.answer}</div>
      {response.queries.map((sql, i) => (
        <details key={i}>
          <summary>SQL</summary>
          <pre>{sql}</pre>
        </details>
      ))}
      {table.length > 0 && (
        <Card>
          <table className="data compact">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c}>{String(row[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {showSuggestions && response.suggestions?.length > 0 && (
        <div className="followups">
          <span className="followups-label">Follow up:</span>
          {response.suggestions.map((s) => (
            <button key={s} className="chip" onClick={() => onPick(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
