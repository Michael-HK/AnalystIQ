import { Badge } from "@/components/ui/badge";

import { Button } from "@/components/ui/button";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { formatCreditPeriodLabel, type CreditRatingOptions } from "@/types/credit-rating";

const AGENCY_DISPLAY_LABELS: Record<string, string> = {
  "Moody's": "Moody",
};

function agencyDisplayLabel(agency: string): string {
  return AGENCY_DISPLAY_LABELS[agency] ?? agency;
}

interface Props {

  options: CreditRatingOptions | null;

  ticker: string;

  selectedAgencies: string[];

  startYear: number;

  endYear: number;

  isRunning: boolean;

  onTickerChange: (value: string) => void;

  onToggleAgency: (agency: string) => void;

  onStartYearChange: (value: number) => void;

  onEndYearChange: (value: number) => void;

  onGenerate: () => void;

  onCancel: () => void;

}



export function CreditRatingConfigPanel({

  options,

  ticker,

  selectedAgencies,

  startYear,

  endYear,

  isRunning,

  onTickerChange,

  onToggleAgency,

  onStartYearChange,

  onEndYearChange,

  onGenerate,

  onCancel,

}: Props) {

  const yearOptions = options?.year_options ?? [];

  const periodInvalid = endYear < startYear;

  const periodLabel = formatCreditPeriodLabel(startYear, endYear);



  return (

    <Card className="h-full">

      <CardHeader>

        <CardTitle className="flex items-center justify-between">

          Credit Rating Workspace

          <Badge variant={isRunning ? "warning" : "default"}>{isRunning ? "Running" : "Ready"}</Badge>

        </CardTitle>

        <CardDescription>Select company, agencies, and the rating period to focus evidence and synthesis.</CardDescription>

      </CardHeader>

      <CardContent className="space-y-4">

        <div className="space-y-2">

          <label className="text-sm font-medium text-slate-700">Ticker</label>

          <select

            className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"

            value={ticker}

            onChange={(event) => onTickerChange(event.target.value)}

            disabled={!options || isRunning}

          >

            {(options?.tickers ?? []).map((item) => (

              <option key={item} value={item}>

                {item}

              </option>

            ))}

          </select>

        </div>



        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/60 p-3">

          <div className="flex items-center justify-between">

            <label className="text-sm font-medium text-slate-700">Rating period</label>

            <Badge variant="default">{periodLabel}</Badge>

          </div>

          <div className="grid grid-cols-2 gap-2">

            <div className="space-y-1">

              <span className="text-xs text-muted-foreground">From year</span>

              <select

                className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"

                value={startYear}

                onChange={(event) => onStartYearChange(Number(event.target.value))}

                disabled={!options || isRunning}

              >

                {yearOptions.map((year) => (

                  <option key={`start-${year}`} value={year}>

                    {year}

                  </option>

                ))}

              </select>

            </div>

            <div className="space-y-1">

              <span className="text-xs text-muted-foreground">To year</span>

              <select

                className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"

                value={endYear}

                onChange={(event) => onEndYearChange(Number(event.target.value))}

                disabled={!options || isRunning}

              >

                {yearOptions.map((year) => (

                  <option key={`end-${year}`} value={year}>

                    {year}

                  </option>

                ))}

              </select>

            </div>

          </div>

          {periodInvalid ? (

            <p className="text-xs text-rose-600">End year must be on or after the start year.</p>

          ) : (

            <p className="text-xs text-muted-foreground">

              {startYear === endYear

                ? "Single-year focus: queries and matrix prioritize that year’s rating evidence."

                : "Range focus: synthesis prioritizes rating actions and outlook within this window."}

            </p>

          )}

        </div>



        <div className="space-y-2">

          <label className="text-sm font-medium text-slate-700">Agencies</label>

          <div className="flex flex-wrap gap-2">

            {(options?.agencies ?? []).map((agency) => {

              const selected = selectedAgencies.includes(agency);

              return (

                <button

                  key={agency}

                  type="button"

                  disabled={isRunning}

                  onClick={() => onToggleAgency(agency)}

                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${

                    selected

                      ? "border-blue-200 bg-blue-100 text-blue-700"

                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"

                  }`}

                >

                  {agencyDisplayLabel(agency)}

                </button>

              );

            })}

          </div>

          <p className="text-xs text-muted-foreground">Select one or more agencies for side-by-side matrix comparison.</p>

        </div>



        <div className="flex gap-2 pt-2">

          <Button

            className="flex-1"

            onClick={onGenerate}

            disabled={!options || isRunning || selectedAgencies.length === 0 || periodInvalid}

          >

            Generate Comparison

          </Button>

          <Button variant="destructive" onClick={onCancel} disabled={!isRunning}>

            Stop

          </Button>

        </div>

      </CardContent>

    </Card>

  );

}


