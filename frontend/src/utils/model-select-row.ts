/**
 * 「模型下拉 + 生成按鈕」單列佈局的共用 className。
 *
 * 多處（分鏡媒體欄、設定集描述/圖片控制項）共用同一套配置：
 * 有模型選項時排成 3 欄網格（選擇器佔 2 欄、按鈕佔 1 欄），
 * 無選項時則讓按鈕靠右固定寬度。集中於此避免各處複製貼上後走樣。
 */

export interface ModelSelectRowClasses {
  /** 外層容器 */
  container: string;
  /** 模型選擇器外層包裹（僅 hasOptions 時使用） */
  select: string;
  /** 生成按鈕 */
  button: string;
}

const SELECT_WRAPPER = "col-span-2 min-w-0";
const BUTTON_BASE = "justify-center h-8 text-xs";

/**
 * @param hasOptions 是否有模型可選（決定網格 vs 靠右佈局）
 * @param marginClass 容器上邊距（各處慣用 `mt-2`/`mt-3`）
 */
export function modelSelectRowClasses(hasOptions: boolean, marginClass = "mt-3"): ModelSelectRowClasses {
  return {
    container: hasOptions ? `${marginClass} grid grid-cols-3 gap-2` : `${marginClass} flex justify-end`,
    select: SELECT_WRAPPER,
    button: `${hasOptions ? "col-span-1 w-full" : "w-28"} ${BUTTON_BASE}`,
  };
}
