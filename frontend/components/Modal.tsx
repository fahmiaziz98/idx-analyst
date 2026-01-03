
import React from 'react';
import { X, AlertCircle, CheckCircle, Info, Trash2 } from 'lucide-react';

export type ModalType = 'alert' | 'confirm' | 'error';

interface ModalProps {
    isOpen: boolean;
    type: ModalType;
    title: string;
    message: string;
    onConfirm?: () => void;
    onClose: () => void;
    confirmText?: string;
    cancelText?: string;
}

const Modal: React.FC<ModalProps> = ({
    isOpen,
    type,
    title,
    message,
    onConfirm,
    onClose,
    confirmText = 'Confirm',
    cancelText = 'Cancel'
}) => {
    if (!isOpen) return null;

    const getIcon = () => {
        switch (type) {
            case 'error':
                return <AlertCircle className="text-red-500" size={24} />;
            case 'confirm':
                return <Trash2 className="text-red-500" size={24} />;
            case 'alert':
            default:
                return <Info className="text-blue-500" size={24} />;
        }
    };

    const getConfirmButtonStyles = () => {
        switch (type) {
            case 'error':
            case 'confirm':
                return 'bg-red-600 hover:bg-red-700 text-white';
            case 'alert':
            default:
                return 'bg-blue-600 hover:bg-blue-700 text-white';
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div
                className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden transform transition-all animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="p-6">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 rounded-full bg-gray-50">
                            {getIcon()}
                        </div>
                        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
                    </div>
                    <p className="text-sm text-gray-600 leading-relaxed mb-6">
                        {message}
                    </p>
                    <div className="flex gap-3 justify-end">
                        {type === 'confirm' && (
                            <button
                                onClick={onClose}
                                className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                            >
                                {cancelText}
                            </button>
                        )}
                        <button
                            onClick={() => {
                                if (onConfirm) onConfirm();
                                else onClose();
                            }}
                            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all active:scale-95 ${getConfirmButtonStyles()}`}
                        >
                            {confirmText}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Modal;
