import React, { useState, useEffect } from 'react';

interface ApiResponse {
  message: string;
}

function App() {
  const [message, setMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMessage = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('Fetching from /api/hello...');

      const response = await fetch('/api/hello');
      console.log('Response status:', response.status);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ApiResponse = await response.json();
      console.log('Data received:', data);
      setMessage(data.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching message:', err);
    } finally {
      setLoading(false);
      console.log('Fetch complete. State:', { loading: false, message, error });
    }
  };

  // Add useEffect to call fetchMessage on mount
  useEffect(() => {
    fetchMessage();
  }, []);

  return (
    <div className="bg-base-200">
      {/* Navigation */}
      <div className="navbar bg-base-100 shadow-lg">
        <div className="flex-1">
          <a className="btn btn-ghost text-xl">PopActa Draft App</a>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-md mx-auto">
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h2 className="card-title justify-center">Backend Message:</h2>
              <p className="text-center text-lg">{message || 'No message yet.'}</p>

              {/* Conditional Rendering for Loading, Error, and Success States */}
              <div className="divider"></div>

              {/* Loading State */}
              {loading && (
                <div className="flex justify-center py-4">
                  <span className="loading loading-spinner loading-md"></span>
                </div>
              )}

              {/* Error State */}
              {error && (
                <div className="alert alert-error">
                  <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Error: {error}</span>
                </div>
              )}

              {/* Success State */}
              {!loading && !error && message && (
                <div className="alert alert-success">
                  <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{message}</span>
                </div>
              )}

              {/* Refresh Button */}
              <div className="card-actions justify-center mt-4">
                <button
                  className="btn btn-primary"
                  onClick={fetchMessage}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="loading loading-spinner loading-sm"></span>
                      Loading...
                    </>
                  ) : (
                    'Refresh Message'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;