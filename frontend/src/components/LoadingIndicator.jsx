import "../styles/LoadingIndicator.css"

function LoadingIndicator() {
    return (
        <div className="loader-container">
            <div className="loader"></div>
            <p>Loading...</p>
        </div>
    );
}

export default LoadingIndicator;
