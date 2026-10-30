import { GuidanceTimelineSection, parseRevisedTimeline } from "@/lib/company";

interface StoryChangedProps {
  guidanceTimeline?: GuidanceTimelineSection | null;
}

export function StoryChanged({ guidanceTimeline }: StoryChangedProps) {
  // Removed from company page
  return null;
}

