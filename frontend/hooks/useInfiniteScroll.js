// hooks/useInfiniteScroll.js
import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook for infinite scroll functionality
 * Handles all the complex intersection observer logic and state management
 * 
 * @param {Function} fetchFunction - Function that fetches more items (receives page number)
 * @param {Object} options - Configuration options
 * @param {number} options.initialPage - Starting page number (default: 0)
 * @param {string} options.rootMargin - Intersection observer root margin (default: '100px')
 * @param {number} options.threshold - Intersection observer threshold (default: 0.1)
 * @returns {Object} - Hook return object with data, loading states, and functions
 */
export const useInfiniteScroll = (fetchFunction, options = {}) => {
  const {
    initialPage = 0,
    rootMargin = '100px',
    threshold = 0.1
  } = options;

  // Core state management
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [page, setPage] = useState(initialPage);
  const [error, setError] = useState(null);

  // Refs for managing observers and preventing duplicate initial loads
  const observerRef = useRef();
  const isInitialLoad = useRef(true);

  // Core fetch function with error handling and state updates
  const fetchMoreItems = useCallback(async () => {
    // Prevent duplicate requests
    if (loading || !hasMore) return;
    
    setLoading(true);
    setError(null);
    
    try {
      console.log(`Fetching page ${page}...`); // Helpful for debugging
      
      const response = await fetchFunction(page);
      
      // Handle different API response formats flexibly
      let newItems, hasMoreData, nextPage;
      
      if (response && typeof response === 'object') {
        // Standard object response: { items: [...], has_more: bool }
        newItems = response.items || response.data || [];
        hasMoreData = response.hasMore ?? response.has_more ?? (newItems.length > 0);
        nextPage = response.nextPage ?? response.next_page ?? page + 1;
      } else if (Array.isArray(response)) {
        // Direct array response
        newItems = response;
        hasMoreData = newItems.length > 0;
        nextPage = page + 1;
      } else {
        // Fallback for unexpected formats
        newItems = [];
        hasMoreData = false;
        nextPage = page + 1;
      }
      
      // Update state with new data
      setItems(prevItems => [...prevItems, ...newItems]);
      setHasMore(hasMoreData);
      setPage(nextPage);
      
      console.log(`Loaded ${newItems.length} items. Has more: ${hasMoreData}`);
      
    } catch (err) {
      console.error('Error fetching items:', err);
      setError(err);
      // Don't increment page on error so retry can work
    } finally {
      setLoading(false);
    }
  }, [fetchFunction, page, loading, hasMore]);

  // Intersection Observer callback - the heart of infinite scroll
  const lastItemRef = useCallback((node) => {
    if (loading) return; // Don't observe while loading
    
    // Disconnect any existing observer
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    
    // Create new observer
    observerRef.current = new IntersectionObserver((entries) => {
      // When the last item becomes visible, fetch more
      if (entries[0].isIntersecting && hasMore && !loading) {
        fetchMoreItems();
      }
    }, {
      rootMargin, // Start loading before reaching the exact bottom
      threshold   // How much of the element needs to be visible
    });
    
    // Observe the new target node
    if (node) {
      observerRef.current.observe(node);
    }
  }, [loading, hasMore, fetchMoreItems, rootMargin, threshold]);

  // Initial load effect - runs once when component mounts
  useEffect(() => {
    if (isInitialLoad.current) {
      fetchMoreItems();
      isInitialLoad.current = false;
    }
  }, []); // Empty dependency array = run once on mount

  // Cleanup effect - prevent memory leaks
  useEffect(() => {
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, []);

  // Reset function for manual refresh (pull-to-refresh, etc.)
  const reset = useCallback(() => {
    setItems([]);
    setPage(initialPage);
    setHasMore(true);
    setError(null);
    setLoading(false);
    isInitialLoad.current = true;
    
    // Disconnect observer to prevent stale observations
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
  }, [initialPage]);

  // Retry function for error recovery
  const retry = useCallback(() => {
    setError(null);
    fetchMoreItems();
  }, [fetchMoreItems]);

  // Manual load more function (for button-based loading)
  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      fetchMoreItems();
    }
  }, [loading, hasMore, fetchMoreItems]);

  return {
    // Core data
    items,
    loading,
    hasMore,
    error,
    
    // Functions
    lastItemRef,    // Attach this to your last item
    reset,          // Call to refresh the entire feed
    retry,          // Call to retry after an error
    loadMore,       // Call to manually load more items
    fetchMoreItems, // Direct access to fetch function
    
    // Computed convenience values
    isEmpty: items.length === 0 && !loading && !error,
    isLoadingInitial: loading && items.length === 0,
    totalItems: items.length
  };
};

export default useInfiniteScroll;
