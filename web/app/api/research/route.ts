import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

const TICKER_REGEX = /^[A-Z0-9&-]{1,20}$/;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const rawTicker = body.ticker;

    if (!rawTicker || typeof rawTicker !== "string") {
      return NextResponse.json(
        { error: "Missing ticker parameter" },
        { status: 400 }
      );
    }

    const ticker = rawTicker.trim().toUpperCase();
    if (!TICKER_REGEX.test(ticker)) {
      return NextResponse.json(
        { error: "Invalid ticker symbol. Use 1–20 uppercase alphanumeric characters, &, or -." },
        { status: 400 }
      );
    }

    // Check existing job in research_jobs
    const { data: job, error: jobError } = await supabase
      .from("research_jobs")
      .select("*")
      .eq("ticker", ticker)
      .maybeSingle();

    if (jobError) {
      console.error("Error querying research_jobs:", jobError);
    }

    // 1. If done within the last 7 days, return "ready"
    if (job?.status === "done" && job.finished_at) {
      const finishedAt = new Date(job.finished_at).getTime();
      const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
      if (finishedAt >= sevenDaysAgo) {
        return NextResponse.json({
          status: "ready",
          ticker,
          finished_at: job.finished_at,
        });
      }
    }

    // 2. If queued or running, return its status
    if (job?.status === "queued" || job?.status === "running") {
      return NextResponse.json({
        status: job.status,
        ticker,
        step: job.step,
        started_at: job.started_at,
        requested_at: job.requested_at,
      });
    }

    // 3. Abuse guard: max 10 dispatches per hour total
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const { count, error: countError } = await supabase
      .from("research_jobs")
      .select("*", { count: "exact", head: true })
      .gte("requested_at", oneHourAgo);

    if (countError) {
      console.warn("Could not check rate limit count:", countError);
    } else if (count !== null && count >= 10) {
      return NextResponse.json(
        { error: "Rate limit reached: at most 10 research requests per hour across all tickers." },
        { status: 429 }
      );
    }

    // 4. Trigger GitHub workflow_dispatch
    const token = process.env.GH_DISPATCH_TOKEN;
    if (!token) {
      return NextResponse.json(
        {
          error:
            "GH_DISPATCH_TOKEN is not configured on the server. Please add your GitHub Personal Access Token to .env.local to dispatch research workflows.",
        },
        { status: 503 }
      );
    }

    const ghRes = await fetch(
      "https://api.github.com/repos/UwUBabushkaUwU/finn/actions/workflows/research.yml/dispatches",
      {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${token}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
          "User-Agent": "FINN-Research-App",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: {
            ticker: ticker,
          },
        }),
      }
    );

    if (!ghRes.ok) {
      const errText = await ghRes.text();
      console.error("GitHub dispatch failed:", ghRes.status, errText);
      return NextResponse.json(
        { error: `GitHub workflow dispatch failed (${ghRes.status}): ${errText || ghRes.statusText}` },
        { status: 502 }
      );
    }

    return NextResponse.json({
      status: "queued",
      ticker,
      message: "Research job dispatched successfully.",
    });
  } catch (err: any) {
    console.error("Unhandled error in /api/research:", err);
    return NextResponse.json(
      { error: err?.message || "Internal server error" },
      { status: 500 }
    );
  }
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const ticker = searchParams.get("ticker")?.trim().toUpperCase();

  if (!ticker) {
    return NextResponse.json({ error: "Missing ticker" }, { status: 400 });
  }

  const { data: job, error } = await supabase
    .from("research_jobs")
    .select("*")
    .eq("ticker", ticker)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ job: job || null });
}
