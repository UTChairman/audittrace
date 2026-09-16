import { useEffect, useRef, useState } from "react";
import type { OcrParagraph } from "../types/api";
import { pageImageUrl } from "../api/client";

type Props = {
  documentId: number;
  pageNumber: number;
  paragraphs: OcrParagraph[];
  highlightedIds: string[];
  intensity?: "cited" | "selected";
  sticky?: boolean;
};

export function PageViewer({
  documentId,
  pageNumber,
  paragraphs,
  highlightedIds,
  intensity = "cited",
  sticky = false,
}: Props) {
  const boxRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [imageReady, setImageReady] = useState(false);

  useEffect(() => {
    setImageReady(false);
  }, [documentId, pageNumber]);

  useEffect(() => {
    if (!imageReady) return;
    const first = highlightedIds[0];
    const node = first ? boxRefs.current[first] : null;
    node?.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  }, [highlightedIds, pageNumber, documentId, imageReady]);

  const highlighted = new Set(highlightedIds);
  const pageParagraphs = paragraphs.filter((paragraph) => paragraph.page_number === pageNumber);
  const fill = intensity === "selected" ? "rgba(232, 196, 74, 0.40)" : "rgba(232, 196, 74, 0.25)";

  return (
    <div
      className={`overflow-auto rounded-lg border border-line bg-[#ece6d8] p-3 shadow-panel ${
        sticky ? "lg:sticky lg:top-4 lg:max-h-[calc(100vh-5.5rem)]" : ""
      }`}
    >
      <div className="relative block w-full">
        <img
          key={`${documentId}-${pageNumber}`}
          src={pageImageUrl(documentId, pageNumber)}
          alt={`Page ${pageNumber}`}
          className="block h-auto w-full"
          onLoad={() => setImageReady(true)}
        />
        <div className="pointer-events-none absolute inset-0">
          {pageParagraphs.map((paragraph) => {
            const active = highlighted.has(paragraph.stable_id);
            return (
              <div
                key={paragraph.stable_id}
                ref={(node) => {
                  boxRefs.current[paragraph.stable_id] = node;
                }}
                className="absolute"
                style={{
                  left: `${paragraph.bbox.x * 100}%`,
                  top: `${paragraph.bbox.y * 100}%`,
                  width: `${paragraph.bbox.width * 100}%`,
                  height: `${paragraph.bbox.height * 100}%`,
                  backgroundColor: active ? fill : "transparent",
                  border: active ? "2px solid #3d5a45" : "2px solid transparent",
                  boxSizing: "border-box",
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
