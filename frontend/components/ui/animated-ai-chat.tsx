"use client";
import React from "react";
import { motion } from "framer-motion";
import { ClaudeChatInput } from "./claude-style-ai-input";

type Props = React.ComponentProps<typeof ClaudeChatInput>;

export function AnimatedAIChat(props: Props) {
  return (
    <div className="w-full flex flex-col items-center justify-center bg-transparent relative overflow-visible">
      <div className="w-full max-w-3xl mx-auto relative z-10">
        <motion.div
          className="relative z-10"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <ClaudeChatInput {...props} />
        </motion.div>
      </div>
    </div>
  );
}
