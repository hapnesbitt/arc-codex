// Filename: /frontend/components/UploadArea.tsx
// Stable, motion-free file upload component
import React from 'react';
import { Upload, CheckCircle } from 'lucide-react';

interface UploadAreaProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
}

function UploadArea({ file, onFileChange, disabled }: UploadAreaProps) {
  const [isDragging, setIsDragging] = React.useState(false);

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileChange(e.dataTransfer.files[0]);
    }
  };

  return (
    <div>
      <label
        htmlFor="file-upload-input"
        className="text-lg font-semibold text-slate-200 flex items-center gap-2 mb-3 cursor-pointer"
      >
        <Upload aria-hidden="true" className="h-5 w-5 text-green-400" />
        Upload File
      </label>
      <div
        className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all ${
          isDragging
            ? 'border-green-400 bg-green-400/5'
            : 'border-slate-600/50 hover:border-green-400/50 hover:bg-green-400/5'
        }`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* opacity-0 input fills the drop zone — keyboard and pointer accessible */}
        <input
          id="file-upload-input"
          type="file"
          onChange={(e) => onFileChange(e.target.files?.[0] || null)}
          accept=".txt,.md,.pdf,.docx,.odt"
          aria-label="Upload file — supports .txt, .md, .pdf, .docx, .odt up to 35MB"
          className="absolute inset-0 opacity-0 cursor-pointer focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-green-400 rounded-xl"
          disabled={disabled}
        />
        <div aria-hidden="true">
          <Upload className="h-12 w-12 text-green-400 mx-auto mb-4" />
          <p className="text-lg font-semibold text-slate-200 mb-2">
            Drop your file here, or click to browse
          </p>
          <p className="text-slate-400 text-sm">
            Supports .txt, .md, .pdf, .docx, .odt files up to 35MB
          </p>
        </div>
        {file && (
          <div className="mt-4 p-4 bg-green-600/10 border border-green-500/30 rounded-lg" role="status">
            <div className="flex items-center gap-3">
              <CheckCircle aria-hidden="true" className="h-5 w-5 text-green-400" />
              <span className="text-green-300 font-medium">{file.name}</span>
              <span className="text-xs bg-slate-700 px-2 py-0.5 rounded">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default React.memo(UploadArea);
