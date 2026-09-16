import { useEffect, useRef, useState } from "react";
import type { OcrParagraph } from "../types/api";
import { pageImageUrl } from "../api/client";

type Props = {
  documentId: number;
  pageNumber: number;
  paragraphs: OcrParagraph[];
  highlightedIds: string[];
};

export function PageViewer({ documentId, pageNumber, paragraphs, highlightedIds }: Props) {
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

  return (
    <div className="overflow-auto rounded-lg border border-line bg-[#ece6d8] p-3 shadow-panel">
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
                className={
                  active
                    ? "absolute border-2 border-forest bg-forest/15"
                    : "absolute border border-transparent"
                }
                style={{
                  left: `${paragraph.bbox.x * 100}%`,
                  top: `${paragraph.bbox.y * 100}%`,
                  width: `${paragraph.bbox.width * 100}%`,
                  height: `${paragraph.bbox.height * 100}%`,
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
