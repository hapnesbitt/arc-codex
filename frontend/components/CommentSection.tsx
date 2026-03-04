// frontend/components/CommentSection.tsx
// TYPESCRIPT CONVERSION: Type-safe comment section with AI-author styling support
// Version 9.0 - REACTIONS + AI COUNTER-ANALYST STYLING + AUTO-POLL
// Features: Max indent depth, smooth animations, mobile-responsive, accessibility,
//           emoji reactions (like/dislike/heart/happy/sad/angry),
//           distinct styling for A.R.C. Counter-Analyst bot comments,
//           auto-polls for new comments every 30s when expanded (catches async AI replies)

'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { MessageSquare, Send, Clock, AlertCircle, Reply, ChevronDown, ChevronRight } from 'lucide-react';
import type { Comment } from '@/lib/types';

// --- TYPE DEFINITIONS ---
interface CommentSectionProps {
  comments?: Comment[];
  articleId: string;
}
interface AuthorStyle {
  icon: React.ReactNode;
  cardClass: string;
  iconBgClass: string;
  authorName: string;
}

interface ApiResponse {
  comment?: Comment;
  error?: string;
}

interface CommentTreeNode extends Comment {
  replies: CommentTreeNode[];
  depth: number;
}

// --- CONFIGURATION ---
const MAX_INDENT_DEPTH = 3; // Facebook-style: stop indenting after 3 levels
const INDENT_WIDTH = 'ml-8'; // 32px indent per level
const INITIAL_VISIBLE_REPLIES = 3; // Show first 3 replies, hide rest behind "View more"

// --- REACTION TYPES ---
const REACTION_TYPES = [
  { key: 'like',    emoji: '👍', label: 'Like' },
  { key: 'dislike', emoji: '👎', label: 'Dislike' },
  { key: 'heart',   emoji: '❤️', label: 'Love' },
  { key: 'happy',   emoji: '😊', label: 'Happy' },
  { key: 'sad',     emoji: '😢', label: 'Sad' },
  { key: 'angry',   emoji: '😡', label: 'Angry' },
] as const;

import { linkifyText } from '@/lib/textUtils';

// --- HELPER: Author styling — outside component, uses no component state ---
const getAuthorStyle = (author?: string): AuthorStyle => {
  if (author === 'A.R.C. Counter-Analyst') {
    return {
      icon: <MessageSquare className="h-4 w-4 text-cyan-300" />,
      cardClass: 'bg-cyan-950/30 border-cyan-500/30 hover:border-cyan-400/50 transition-colors',
      iconBgClass: 'bg-gradient-to-br from-cyan-500/30 to-blue-600/30 border-cyan-400/40',
      authorName: '🤖 A.R.C. Counter-Analyst'
    };
  }
  return {
    icon: <MessageSquare className="h-4 w-4 text-amber-300" />,
    cardClass: 'bg-slate-900/40 border-slate-700/30 hover:border-slate-600/50 transition-colors',
    iconBgClass: 'bg-gradient-to-br from-amber-500/30 to-amber-600/30 border-amber-400/40',
    authorName: author || 'User'
  };
};

function CommentSection({ comments = [], articleId }: CommentSectionProps): React.JSX.Element {
  const [commentText, setCommentText] = useState<string>('');
  const [localComments, setLocalComments] = useState<Comment[]>(comments);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState<string>('');
  const [collapsedThreads, setCollapsedThreads] = useState<Set<string>>(new Set());
  const [expandedReplies, setExpandedReplies] = useState<Set<string>>(new Set());
  // Track which reactions the current user has toggled (per session)
  const [userReactions, setUserReactions] = useState<Record<string, Set<string>>>({});

  // --- AUTO-POLL FOR NEW COMMENTS (catches AI replies that arrive asynchronously) ---
  const POLL_INTERVAL = 30000; // 30 seconds

  const fetchLatestComments = useCallback(async () => {
    try {
      const response = await fetch(`/api/article/${articleId}/comments`);
      if (!response.ok) return;
      const freshComments: Comment[] = await response.json();
      
      // Only update if comment count changed (avoids unnecessary re-renders)
      if (freshComments.length !== localComments.length) {
        setLocalComments(freshComments);
      }
    } catch (err) {
      // Silent fail — polling is best-effort
      console.debug('Comment poll failed:', err);
    }
  }, [articleId, localComments.length]);

  useEffect(() => {
    if (!isExpanded) return;
    
    const interval = setInterval(fetchLatestComments, POLL_INTERVAL);
    
    // Also fetch immediately when expanding (catches replies that arrived while collapsed)
    fetchLatestComments();
    
    return () => clearInterval(interval);
  }, [isExpanded, fetchLatestComments]);

  // Build comment tree structure with depth tracking
  const commentTree = useMemo<CommentTreeNode[]>(() => {
    const commentsById = new Map<string, CommentTreeNode>();
    const rootComments: CommentTreeNode[] = [];

    // First pass: create nodes
    localComments.forEach(comment => {
      commentsById.set(comment.id, { ...comment, replies: [], depth: 0 });
    });

    // Second pass: build tree and calculate depths
    localComments.forEach(comment => {
      const node = commentsById.get(comment.id)!;
      if (comment.parent_id && commentsById.has(comment.parent_id)) {
        const parent = commentsById.get(comment.parent_id)!;
        node.depth = parent.depth + 1;
        parent.replies.push(node);
      } else {
        rootComments.push(node);
      }
    });

    // Sort by timestamp (oldest first for chronological reading)
    const sortByTimestamp = (a: CommentTreeNode, b: CommentTreeNode) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();

    const sortReplies = (nodes: CommentTreeNode[]) => {
      nodes.sort(sortByTimestamp);
      nodes.forEach(node => sortReplies(node.replies));
    };

    rootComments.sort(sortByTimestamp);
    sortReplies(rootComments);

    return rootComments;
  }, [localComments]);

  const handleSubmitComment = async (e: React.FormEvent, parentId: string = '') => {
    e.preventDefault();
    const textToSubmit = parentId ? replyText : commentText;
    
    if (!textToSubmit.trim()) { 
      setError('Please enter a comment before submitting.'); 
      return; 
    }
    
    setIsSubmitting(true);
    setError('');
    
    try {
      const response = await fetch('/api/submit_comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          article_id: articleId, 
          comment_text: textToSubmit.trim(),
          parent_id: parentId 
        }),
      });
      
      const data: ApiResponse = await response.json();
      
      if (response.ok && data.comment) {
        setLocalComments(prev => [...prev, data.comment!]);
        if (parentId) {
          setReplyText('');
          setReplyingTo(null);
        } else {
          setCommentText('');
        }
        setError('');
      } else {
        setError(data.error || 'Failed to post comment. Please try again.');
      }
    } catch (err) {
      console.error('Error submitting comment:', err);
      setError('Network error. Please check your connection and try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      // Facebook-style relative time
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m`;
      if (diffHours < 24) return `${diffHours}h`;
      if (diffDays < 7) return `${diffDays}d`;
      
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { 
      return 'Recently'; 
    }
  };

  const toggleThread = (commentId: string) => {
    setCollapsedThreads(prev => {
      const newSet = new Set(prev);
      if (newSet.has(commentId)) {
        newSet.delete(commentId);
      } else {
        newSet.add(commentId);
      }
      return newSet;
    });
  };

  const toggleShowAllReplies = (commentId: string) => {
    setExpandedReplies(prev => {
      const newSet = new Set(prev);
      if (newSet.has(commentId)) {
        newSet.delete(commentId);
      } else {
        newSet.add(commentId);
      }
      return newSet;
    });
  };

  const handleReaction = async (commentId: string, reactionKey: string) => {
    const userSet = userReactions[commentId] || new Set<string>();
    const alreadyReacted = userSet.has(reactionKey);
    const action = alreadyReacted ? 'remove' : 'add';

    // Optimistic update
    setUserReactions(prev => {
      const newSet = new Set(prev[commentId] || []);
      if (alreadyReacted) {
        newSet.delete(reactionKey);
      } else {
        newSet.add(reactionKey);
      }
      return { ...prev, [commentId]: newSet };
    });

    setLocalComments(prev => prev.map(c => {
      if (c.id !== commentId) return c;
      const reactions = { ...(c.reactions || {}) };
      reactions[reactionKey] = (reactions[reactionKey] || 0) + (alreadyReacted ? -1 : 1);
      if (reactions[reactionKey] <= 0) delete reactions[reactionKey];
      return { ...c, reactions };
    }));

    // Fire and forget — optimistic update already applied
    try {
      await fetch(`/api/comment/${commentId}/react`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reaction: reactionKey, action }),
      });
    } catch (err) {
      console.error('Reaction failed:', err);
    }
  };

  const renderComment = (comment: CommentTreeNode, depth: number = 0) => {
    const style = getAuthorStyle(comment.author);
    const isCollapsed = collapsedThreads.has(comment.id);
    const hasReplies = comment.replies.length > 0;
    const isReplyFormOpen = replyingTo === comment.id;
    const shouldIndent = depth > 0 && depth <= MAX_INDENT_DEPTH;
    const effectiveDepth = Math.min(depth, MAX_INDENT_DEPTH);
    const showAllReplies = expandedReplies.has(comment.id);
    const visibleReplies = showAllReplies ? comment.replies : comment.replies.slice(0, INITIAL_VISIBLE_REPLIES);
    const hasHiddenReplies = comment.replies.length > INITIAL_VISIBLE_REPLIES && !showAllReplies;

    return (
      <div key={comment.id} className="relative">
        <motion.div
          initial={{ opacity: 0, x: shouldIndent ? 20 : 0 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          className={shouldIndent ? INDENT_WIDTH : ''}
        >
          {/* Connection line for nested comments (Facebook-style) */}
          {shouldIndent && (
            <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-slate-700/30" 
                 style={{ marginLeft: '-16px' }} />
          )}

          <Card className={style.cardClass}>
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <div className={`w-8 h-8 rounded-full border flex items-center justify-center flex-shrink-0 ${style.iconBgClass}`}>
                  {style.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-slate-200 text-sm">{style.authorName}</span>
                    <span className="text-xs text-slate-500">•</span>
                    <span className="text-xs text-slate-500">{formatTimestamp(comment.timestamp)}</span>
                  </div>
                  <div 
                    className="text-slate-200 leading-relaxed mb-2 whitespace-pre-wrap text-sm prose prose-invert max-w-none"
                    dangerouslySetInnerHTML={{ __html: linkifyText(comment.text) }}
                  />
                  
                  {/* Action buttons - Facebook style */}
                  <div className="flex items-center gap-4 text-xs">
                    <button
                      onClick={() => setReplyingTo(comment.id)}
                      className="text-slate-400 hover:text-amber-400 transition-colors font-semibold flex items-center gap-1"
                    >
                      <Reply className="h-3 w-3" />
                      <span>Reply</span>
                    </button>
                    {hasReplies && (
                      <button
                        onClick={() => toggleThread(comment.id)}
                        className="text-slate-400 hover:text-slate-300 transition-colors font-semibold flex items-center gap-1"
                      >
                        {isCollapsed ? (
                          <>
                            <ChevronRight className="h-3 w-3" />
                            <span>{comment.replies.length} {comment.replies.length === 1 ? 'reply' : 'replies'}</span>
                          </>
                        ) : (
                          <>
                            <ChevronDown className="h-3 w-3" />
                            <span>Hide</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>

                  {/* Reaction bar */}
                  <div className="flex items-center gap-1 mt-2 flex-wrap">
                    {REACTION_TYPES.map(({ key, emoji, label }) => {
                      const count = comment.reactions?.[key] || 0;
                      const isActive = userReactions[comment.id]?.has(key) || false;
                      const showCount = count > 0;
                      return (
                        <button
                          key={key}
                          onClick={() => handleReaction(comment.id, key)}
                          title={label}
                          className={`
                            flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-all duration-200
                            ${isActive 
                              ? 'bg-amber-500/20 border border-amber-400/40 scale-105' 
                              : 'bg-slate-800/40 border border-slate-700/30 hover:bg-slate-700/50 hover:border-slate-600/40'
                            }
                          `}
                        >
                          <span className={`text-sm ${isActive ? 'scale-110' : 'grayscale-[30%]'} transition-transform`}>
                            {emoji}
                          </span>
                          {showCount && (
                            <span className={`font-medium ${isActive ? 'text-amber-300' : 'text-slate-400'}`}>
                              {count}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Inline Reply Form */}
              <AnimatePresence>
                {isReplyFormOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="mt-4 ml-11"
                  >
                    <form onSubmit={(e) => handleSubmitComment(e, comment.id)} className="space-y-3">
                      <textarea
                        value={replyText}
                        onChange={(e) => setReplyText(e.target.value)}
                        placeholder={`Reply to ${style.authorName}...`}
                        className="w-full p-3 bg-slate-900/60 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-400 resize-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all text-sm"
                        rows={2}
                        maxLength={9000}
                        disabled={isSubmitting}
                        autoFocus
                      />
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-slate-400">
                          {replyText.length}/9000
                        </span>
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setReplyingTo(null);
                              setReplyText('');
                            }}
                            className="text-slate-400 hover:text-white h-8"
                          >
                            Cancel
                          </Button>
                          <Button
                            type="submit"
                            variant="default"
                            size="sm"
                            disabled={isSubmitting || !replyText.trim()}
                            className="bg-amber-600/80 hover:bg-amber-500/80 text-white border-0 h-8"
                          >
                            {isSubmitting ? (
                              <div className="flex items-center gap-2">
                                <div className="w-3 h-3 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                <span>Posting...</span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1.5">
                                <Send className="h-3 w-3" />
                                <span>Reply</span>
                              </div>
                            )}
                          </Button>
                        </div>
                      </div>
                    </form>
                  </motion.div>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>
        </motion.div>

        {/* Render replies */}
        <AnimatePresence>
          {hasReplies && !isCollapsed && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
              className="space-y-3 mt-3"
            >
              {visibleReplies.map(reply => renderComment(reply, depth + 1))}
              
              {/* "View more replies" button - Facebook style */}
              {hasHiddenReplies && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className={shouldIndent ? INDENT_WIDTH : ''}
                >
                  <button
                    onClick={() => toggleShowAllReplies(comment.id)}
                    className="flex items-center gap-2 text-amber-400 hover:text-amber-300 transition-colors text-sm font-semibold ml-11"
                  >
                    <ChevronDown className="h-4 w-4" />
                    <span>View {comment.replies.length - INITIAL_VISIBLE_REPLIES} more {comment.replies.length - INITIAL_VISIBLE_REPLIES === 1 ? 'reply' : 'replies'}</span>
                  </button>
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  const totalComments = localComments.length;

  return (
    <div className="border-t border-slate-700/50 pt-6">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-slate-300 hover:text-amber-300 transition-colors group"
          aria-expanded={isExpanded}
          aria-label={`${isExpanded ? 'Hide' : 'Show'} comments`}
        >
          <MessageSquare className="h-5 w-5 group-hover:scale-110 transition-transform" />
          <span className="font-medium">
            {totalComments} Comment{totalComments !== 1 ? 's' : ''}
          </span>
          <motion.div 
            animate={{ rotate: isExpanded ? 180 : 0 }} 
            transition={{ duration: 0.2 }} 
            className="ml-1"
          >
            <ChevronDown className="h-4 w-4" />
          </motion.div>
        </button>
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="space-y-4"
          >
            {/* Top-level Comment Form */}
            <Card className="bg-slate-800/40 border-slate-700/40">
              <CardContent className="p-4">
                <form onSubmit={(e) => handleSubmitComment(e)} className="space-y-4">
                  <div>
                    <textarea 
                      value={commentText} 
                      onChange={(e) => setCommentText(e.target.value)} 
                      placeholder="Share your thoughts on this article..." 
                      className="w-full p-3 bg-slate-900/60 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-400 resize-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all" 
                      rows={3} 
                      maxLength={9000} 
                      disabled={isSubmitting}
                      aria-label="Write a comment"
                    />
                    <div className="flex justify-between items-center mt-2">
                      <span className="text-xs text-slate-400">
                        {commentText.length}/9000 characters
                      </span>
                    </div>
                  </div>
                  
                  {error && (
                    <motion.div 
                      initial={{ opacity: 0, y: -10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3"
                      role="alert"
                    >
                      <AlertCircle className="h-4 w-4 flex-shrink-0" />
                      <span>{error}</span>
                    </motion.div>
                  )}
                  
                  <div className="flex justify-end">
                    <Button 
                      type="submit" 
                      variant="default"
                      size="default"
                      disabled={isSubmitting || !commentText.trim()} 
                      className="bg-amber-600/80 hover:bg-amber-500/80 text-white border-0 px-6"
                    >
                      {isSubmitting ? (
                        <div className="flex items-center gap-2">
                          <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                          <span>Posting...</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Send className="h-4 w-4" />
                          <span>Post Comment</span>
                        </div>
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* Comments Tree */}
            <div className="space-y-4">
              <AnimatePresence mode="popLayout">
                {commentTree.length === 0 ? (
                  <motion.div 
                    initial={{ opacity: 0 }} 
                    animate={{ opacity: 1 }} 
                    className="text-center py-8 text-slate-400"
                  >
                    <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>No comments yet. Be the first to share your thoughts!</p>
                  </motion.div>
                ) : (
                  commentTree.map((comment) => renderComment(comment))
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default React.memo(CommentSection);
