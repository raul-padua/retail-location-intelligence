"use client";

/**
 * The verified metric registry: the only route from a retail concept to an Atlas
 * identifier. Nothing outside this table can be requested.
 */

import { titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Card, Cell, Table } from "../ui";
import { CapabilityList } from "./CapabilityList";

export function RegistryPanel() {
  const { catalog } = useSession();
  const metrics = catalog?.metrics ?? [];

  return (
    <div className="space-y-6">
      <Card
        title="Verified metric registry"
        description={`${metrics.length} datapoints, each confirmed live against Atlas. A metric that has not been verified cannot be loaded.`}
      >
        <Table
          columns={[
            "Metric",
            "Atlas datapoint",
            "Category",
            "Unit",
            "Direction",
            "Levels",
            "Why it may matter",
          ]}
          dense
        >
          {metrics.map((metric) => (
            <tr key={metric.metric_id}>
              <Cell className="font-medium text-slate-900">
                {metric.display_name}
              </Cell>
              <Cell className="font-mono text-xs text-slate-600">
                {metric.atlas_datapoint}
                {metric.atlas_item_code ? (
                  <span className="text-slate-400"> [{metric.atlas_item_code}]</span>
                ) : null}
              </Cell>
              <Cell>{metric.category_label}</Cell>
              <Cell className="text-xs">{metric.unit}</Cell>
              <Cell className="text-xs">{titleCase(metric.direction)}</Cell>
              <Cell className="text-xs text-slate-500">
                {metric.supported_geography_types.join(", ")}
              </Cell>
              <Cell className="max-w-sm text-slate-600">
                {metric.retail_rationale}
              </Cell>
            </tr>
          ))}
        </Table>
      </Card>

      <Card title="Governed capabilities">
        <CapabilityList />
      </Card>
    </div>
  );
}
