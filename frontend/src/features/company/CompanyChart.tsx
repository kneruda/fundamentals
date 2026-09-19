import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

type CompanyChartProps = {
  label: string;
  option: EChartsOption;
  height?: "standard" | "tall";
};

export function CompanyChart({ label, option, height = "standard" }: CompanyChartProps) {
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const chart = echarts.init(element, undefined, { renderer: "canvas" });
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);

    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div aria-label={label} className={`company-chart company-chart--${height}`} ref={elementRef} />;
}
