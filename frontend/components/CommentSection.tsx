// frontend/components/CommentSection.tsx
// Version 10.0 - Layout fixes + accessibility pass
//
// Layout changes from v9.0:
// - Indent reduced: ml-8 → ml-4 sm:ml-6 (mobile gets 16px, desktop 24px)
// - Reply form indent: ml-11 → ml-0 sm:ml-10 (no indent on mobile)
// - "View more replies" button: ml-11 removed, indent handled by parent
// - Icon column hidden at depth >= 2 on mobile to recover horizontal space
// - Card padding: p-4 on mobile, keeps breathing room at all depths
// - Connection line position adjusted to match new indent
//
// Accessibility changes from v9.0:
// - Comment list wrapped in <ol> (ordered, chronological — correct semantic)
// - Each comment is a <li> (correct, not a div)
// - Reply form: aria-label on textarea includes author name
// - Reaction buttons: aria-label="[label] ([count])" replaces title-only
// - aria-pressed on reaction buttons (toggle state)
// - Collapse/expand thread: aria-expanded + aria-controls
// - "View more replies" button: aria-label with count
// - Icons throughout: aria-hidden="true"
// - Error div already has role="alert" — retained
// - Comment timestamp: <time> element with dateTime attribute
// - Empty state: role="status" so AT announces it
// - Top-level comment textarea: aria-label already present — retained
// - Loading spinners: aria-hidden (visual only, button label covers state)
// - Comment section toggle: aria-expanded already present — retained

'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { MessageSquare, Send, AlertCircle, Reply, ChevronDown, ChevronRight } from 'lucide-react';
import type { Comment } from '@/lib/types';
import { linkifyText } from '@/lib/textUtils';

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
const MAX_INDENT_DEPTH = 3;
const INITIAL_VISIBLE_REPLIES = 3;

// --- REACTION TYPES ---
const REACTION_TYPES = [
  { key: 'like',    emoji: '👍', label: 'Like' },
  { key: 'dislike', emoji: '👎', label: 'Dislike' },
  { key: 'heart',   emoji: '❤️', label: 'Love' },
  { key: 'happy',   emoji: '😊', label: 'Happy' },
  { key: 'sad',     emoji: '😢', label: 'Sad' },
  { key: 'angry',   emoji: '😡', label: 'Angry' },
] as const;

// --- HELPER: Author styling ---
const getAuthorStyle = (author?: string): AuthorStyle => {
  if (author === 'A.R.C. Counter-Analyst') {
    return {
      icon: <MessageSquare className="h-4 w-4 text-cyan-300" aria-hidden="true" />,
      cardClass: 'bg-cyan-950/30 border-cyan-500/30 hover:border-cyan-400/50 transition-colors',
      iconBgClass: 'bg-gradient-to-br from-cyan-500/30 to-blue-600/30 border-cyan-400/40',
      authorName: '🤖 A.R.C. Counter-Analyst',
    };
  }
  return {
    icon: <MessageSquare className="h-4 w-4 text-amber-300" aria-hidden="true" />,
    cardClass: 'bg-slate-900/40 border-slate-700/30 hover:border-slate-600/50 transition-colors',
    iconBgClass: 'bg-gradient-to-br from-amber-500/30 to-amber-600/30 border-amber-400/40',
    authorName: author || 'User',
  };
};

function CommentSection({ comments = [], articleId }: CommentSectionProps): React.JSX.Element {
  const [commentText, setCommentText]       = useState<string>('');
  const [localComments, setLocalComments]   = useState<Comment[]>(comments);
  const [isSubmitting, setIsSubmitting]     = useState<boolean>(false);
  const [error, setError]                   = useState<string>('');
  const [isExpanded, setIsExpanded]         = useState<boolean>(false);
  const [replyingTo, setReplyingTo]         = useState<string | null>(null);
  const [replyText, setReplyText]           = useState<string>('');
  const [collapsedThreads, setCollapsedThreads] = useState<Set<string>>(new Set());
  const [expandedReplies, setExpandedReplies]   = useState<Set<string>>(new Set());
  const [userReactions, setUserReactions]   = useState<Record<string, Set<string>>>({});

  // --- AUTO-POLL (catches async AI replies) ---
  const POLL_INTERVAL = 30000;

  const fetchLatestComments = useCallback(async () => {
    try {
      const response = await fetch(`/api/article/${articleId}/comments`);
      if (!response.ok) return;
      const freshComments: Comment[] = await response.json();
      if (freshComments.length !== localComments.length) {
        setLocalComments(freshComments);
      }
    } catch (err) {
      console.debug('Comment poll failed:', err);
    }
  }, [articleId, localComments.length]);

  useEffect(() => {
    if (!isExpanded) return;
    const interval = setInterval(fetchLatestComments, POLL_INTERVAL);
    fetchLatestComments();
    return () => clearInterval(interval);
  }, [isExpanded, fetchLatestComments]);

  // --- COMMENT TREE ---
  const commentTree = useMemo<CommentTreeNode[]>(() => {
    const commentsById = new Map<string, CommentTreeNode>();
    const rootComments: CommentTreeNode[] = [];

    localComments.forEach(comment => {
      commentsById.set(comment.id, { ...comment, replies: [], depth: 0 });
    });

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

  // --- SUBMIT ---
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
          parent_id: parentId,
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

  const formatTimestamp = (timestamp: string): { relative: string; iso: string } => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);
      let relative: string;
      if (diffMins < 1) relative = 'Just now';
      else if (diffMins < 60) relative = `${diffMins}m`;
      else if (diffHours < 24) relative = `${diffHours}h`;
      else if (diffDays < 7) relative = `${diffDays}d`;
      else relative = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      return { relative, iso: date.toISOString() };
    } catch {
      return { relative: 'Recently', iso: '' };
    }
  };

  const toggleThread = (commentId: string) => {
    setCollapsedThreads(prev => {
      const s = new Set(prev);
      s.has(commentId) ? s.delete(commentId) : s.add(commentId);
      return s;
    });
  };

  const toggleShowAllReplies = (commentId: string) => {
    setExpandedReplies(prev => {
      const s = new Set(prev);
      s.has(commentId) ? s.delete(commentId) : s.add(commentId);
      return s;
    });
  };

  const handleReaction = async (commentId: string, reactionKey: string) => {
    const userSet = userReactions[commentId] || new Set<string>();
    const alreadyReacted = userSet.has(reactionKey);
    const action = alreadyReacted ? 'remove' : 'add';

    setUserReactions(prev => {
      const s = new Set(prev[commentId] || []);
      alreadyReacted ? s.delete(reactionKey) : s.add(reactionKey);
      return { ...prev, [commentId]: s };
    });

    setLocalComments(prev => prev.map(c => {
      if (c.id !== commentId) return c;
      const reactions = { ...(c.reactions || {}) };
      reactions[reactionKey] = (reactions[reactionKey] || 0) + (alreadyReacted ? -1 : 1);
      if (reactions[reactionKey] <= 0) delete reactions[reactionKey];
      return { ...c, reactions };
    }));

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

  // --- RENDER COMMENT ---
  const renderComment = (comment: CommentTreeNode, depth: number = 0) => {
    const style = getAuthorStyle(comment.author);
    const isCollapsed = collapsedThreads.has(comment.id);
    const hasReplies = comment.replies.length > 0;
    const isReplyFormOpen = replyingTo === comment.id;
    const shouldIndent = depth > 0 && depth <= MAX_INDENT_DEPTH;
    const showAllReplies = expandedReplies.has(comment.id);
    const visibleReplies = showAllReplies
      ? comment.replies
      : comment.replies.slice(0, INITIAL_VISIBLE_REPLIES);
    const hasHiddenReplies = comment.replies.length > INITIAL_VISIBLE_REPLIES && !showAllReplies;
    const hiddenCount = comment.replies.length - INITIAL_VISIBLE_REPLIES;
    const repliesId = `replies-${comment.id}`;
    const ts = formatTimestamp(comment.timestamp);

    // On mobile, hide the avatar icon at depth >= 2 to recover horizontal space.
    // At those depths the indent + card padding already eats most of the viewport.
    const showIcon = depth < 2;

    return (
      // <li> is correct inside the parent <ol>
      <li key={comment.id} className="relative list-none">
        <motion.div
          initial={{ opacity: 0, x: shouldIndent ? 10 : 0 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          // Mobile: 16px indent. sm+: 24px indent. Keeps content readable on small screens.
          className={shouldIndent ? 'ml-4 sm:ml-6' : ''}
        >
          {/* Thread connection line — decorative */}
          {shouldIndent && (
            <div
              className="absolute left-0 top-0 bottom-0 w-0.5 bg-slate-700/30"
              style={{ marginLeft: '-8px' }}
              aria-hidden="true"
            />
          )}

          <Card className={style.cardClass}>
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-start gap-2 sm:gap-3">
                {/* Avatar icon — hidden at deep nesting on mobile to save space */}
                {showIcon && (
                  <div
                    className={`w-7 h-7 sm:w-8 sm:h-8 rounded-full border flex items-center justify-center flex-shrink-0 ${style.iconBgClass}`}
                    aria-hidden="true"
                  >
                    {style.icon}
                  </div>
                )}

                <div className="flex-1 min-w-0">
                  {/* Author + timestamp */}
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-semibold text-slate-200 text-sm">{style.authorName}</span>
                    <span className="text-xs text-slate-500" aria-hidden="true">•</span>
                    <time
                      dateTime={ts.iso}
                      className="text-xs text-slate-500"
                      title={ts.iso ? new Date(ts.iso).toLocaleString() : ''}
                    >
                      {ts.relative}
                    </time>
                  </div>

                  {/* Comment body */}
                  <div
                    className="text-slate-200 leading-relaxed mb-2 whitespace-pre-wrap text-sm prose prose-invert max-w-none"
                    dangerouslySetInnerHTML={{ __html: linkifyText(comment.text) }}
                  />

                  {/* Action row */}
                  <div className="flex items-center gap-3 text-xs">
                    <button
                      onClick={() => setReplyingTo(isReplyFormOpen ? null : comment.id)}
                      aria-expanded={isReplyFormOpen}
                      aria-label={`Reply to ${style.authorName}`}
                      className="text-slate-400 hover:text-amber-400 transition-colors font-semibold flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber-400/50 rounded"
                    >
                      <Reply className="h-3 w-3" aria-hidden="true" />
                      <span>Reply</span>
                    </button>

                    {hasReplies && (
                      <button
                        onClick={() => toggleThread(comment.id)}
                        aria-expanded={!isCollapsed}
                        aria-controls={repliesId}
                        className="text-slate-400 hover:text-slate-300 transition-colors font-semibold flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-slate-400/50 rounded"
                      >
                        {isCollapsed ? (
                          <>
                            <ChevronRight className="h-3 w-3" aria-hidden="true" />
                            <span>{comment.replies.length} {comment.replies.length === 1 ? 'reply' : 'replies'}</span>
                          </>
                        ) : (
                          <>
                            <ChevronDown className="h-3 w-3" aria-hidden="true" />
                            <span>Hide</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>

                  {/* Reaction bar */}
                  <div className="flex items-center gap-1 mt-2 flex-wrap" role="group" aria-label="Reactions">
                    {REACTION_TYPES.map(({ key, emoji, label }) => {
                      const count = comment.reactions?.[key] || 0;
                      const isActive = userReactions[comment.id]?.has(key) || false;
                      return (
                        <button
                          key={key}
                          onClick={() => handleReaction(comment.id, key)}
                          aria-pressed={isActive}
                          aria-label={count > 0 ? `${label}: ${count}` : label}
                          className={`
                            flex items-center gap-1 px-2 py-0.5 rounded-full text-xs transition-all duration-200
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50
                            ${isActive
                              ? 'bg-amber-500/20 border border-amber-400/40 scale-105'
                              : 'bg-slate-800/40 border border-slate-700/30 hover:bg-slate-700/50 hover:border-slate-600/40'
                            }
                          `}
                        >
                          <span className={`text-sm ${isActive ? 'scale-110' : 'grayscale-[30%]'} transition-transform`} aria-hidden="true">
                            {emoji}
                          </span>
                          {count > 0 && (
                            <span className={`font-medium ${isActive ? 'text-amber-300' : 'text-slate-400'}`} aria-hidden="true">
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
                    // No left indent on mobile — card width is already constrained.
                    // sm+ gets the indent to visually align under the comment text.
                    className="mt-3 sm:ml-9"
                  >
                    <form onSubmit={(e) => handleSubmitComment(e, comment.id)} className="space-y-3">
                      <div>
                        <label htmlFor={`reply-${comment.id}`} className="sr-only">
                          Reply to {style.authorName}
                        </label>
                        <textarea
                          id={`reply-${comment.id}`}
                          value={replyText}
                          onChange={(e) => setReplyText(e.target.value)}
                          placeholder={`Reply to ${style.authorName}...`}
                          className="w-full p-3 bg-slate-900/60 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-400 resize-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all text-sm"
                          rows={2}
                          maxLength={9000}
                          disabled={isSubmitting}
                          autoFocus
                        />
                        <div className="flex justify-between items-center mt-1">
                          <span className="text-xs text-slate-500">{replyText.length}/9000</span>
                        </div>
                      </div>
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => { setReplyingTo(null); setReplyText(''); }}
                          className="text-slate-400 hover:text-white h-8"
                        >
                          Cancel
                        </Button>
                        <Button
                          type="submit"
                          variant="default"
                          size="sm"
                          disabled={isSubmitting || !replyText.trim()}
                          aria-label={isSubmitting ? 'Posting reply' : 'Post reply'}
                          className="bg-amber-600/80 hover:bg-amber-500/80 text-white border-0 h-8"
                        >
                          {isSubmitting ? (
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 border-2 border-white/20 border-t-white rounded-full animate-spin" aria-hidden="true" />
                              <span>Posting...</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5">
                              <Send className="h-3 w-3" aria-hidden="true" />
                              <span>Reply</span>
                            </div>
                          )}
                        </Button>
                      </div>
                    </form>
                  </motion.div>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>
        </motion.div>

        {/* Replies */}
        <AnimatePresence>
          {hasReplies && !isCollapsed && (
            <motion.ol
              id={repliesId}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
              className="space-y-3 mt-3"
              aria-label={`Replies to ${style.authorName}`}
            >
              {visibleReplies.map(reply => renderComment(reply, depth + 1))}

              {hasHiddenReplies && (
                <motion.li
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="list-none"
                >
                  <button
                    onClick={() => toggleShowAllReplies(comment.id)}
                    aria-label={`View ${hiddenCount} more ${hiddenCount === 1 ? 'reply' : 'replies'}`}
                    className="flex items-center gap-2 text-amber-400 hover:text-amber-300 transition-colors text-sm font-semibold ml-4 sm:ml-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 rounded"
                  >
                    <ChevronDown className="h-4 w-4" aria-hidden="true" />
                    <span>View {hiddenCount} more {hiddenCount === 1 ? 'reply' : 'replies'}</span>
                  </button>
                </motion.li>
              )}
            </motion.ol>
          )}
        </AnimatePresence>
      </li>
    );
  };

  const totalComments = localComments.length;

  return (
    <section aria-label="Comments" className="border-t border-slate-700/50 pt-6">
      {/* Toggle header */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          aria-expanded={isExpanded}
          aria-controls="comment-thread"
          className="flex items-center gap-2 text-slate-300 hover:text-amber-300 transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 rounded"
        >
          <MessageSquare className="h-5 w-5 group-hover:scale-110 transition-transform" aria-hidden="true" />
          <span className="font-medium">
            {totalComments} {totalComments === 1 ? 'Comment' : 'Comments'}
          </span>
          <motion.div
            animate={{ rotate: isExpanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
            className="ml-1"
            aria-hidden="true"
          >
            <ChevronDown className="h-4 w-4" />
          </motion.div>
        </button>
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            id="comment-thread"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="space-y-4"
          >
            {/* Comment submission form */}
            <Card className="bg-slate-800/40 border-slate-700/40">
              <CardContent className="p-4">
                <form onSubmit={(e) => handleSubmitComment(e)} className="space-y-4" noValidate>
                  <div>
                    <label htmlFor="new-comment" className="sr-only">Write a comment</label>
                    <textarea
                      id="new-comment"
                      value={commentText}
                      onChange={(e) => setCommentText(e.target.value)}
                      placeholder="Share your thoughts on this article..."
                      className="w-full p-3 bg-slate-900/60 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-400 resize-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-all"
                      rows={3}
                      maxLength={9000}
                      disabled={isSubmitting}
                    />
                    <div className="flex justify-between items-center mt-2">
                      <span className="text-xs text-slate-400" aria-live="polite" aria-atomic="true">
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
                      <AlertCircle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      <span>{error}</span>
                    </motion.div>
                  )}

                  <div className="flex justify-end">
                    <Button
                      type="submit"
                      variant="default"
                      size="default"
                      disabled={isSubmitting || !commentText.trim()}
                      aria-label={isSubmitting ? 'Posting comment' : 'Post comment'}
                      className="bg-amber-600/80 hover:bg-amber-500/80 text-white border-0 px-6"
                    >
                      {isSubmitting ? (
                        <div className="flex items-center gap-2">
                          <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" aria-hidden="true" />
                          <span>Posting...</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Send className="h-4 w-4" aria-hidden="true" />
                          <span>Post Comment</span>
                        </div>
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* Comment tree */}
            {commentTree.length === 0 ? (
              <div
                role="status"
                className="text-center py-8 text-slate-400"
              >
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" aria-hidden="true" />
                <p>No comments yet. Be the first to share your thoughts!</p>
              </div>
            ) : (
              <ol className="space-y-4" aria-label="Comments">
                <AnimatePresence mode="popLayout">
                  {commentTree.map((comment) => renderComment(comment))}
                </AnimatePresence>
              </ol>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

export default React.memo(CommentSection);
