# client_example.py
# Example client code to test file upload/download

import requests

def upload_file(file_path, api_url):
    # Upload a file to the serivce
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{api_url}/upload/", files=files)

    return response.json()

def download_file(file_hash, output_path, api_url):
    # Download a file from the service
    response = requests.get(f"{api_url}/download/{file_hash}", stream=True)

    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
            return True
    return False

def list_files(api_url):
    # List all files in the serivce
    response = requests.get(f"{api_url}/files/")
    return response.json()

# Example usage
if __name__ == "__main__":
    API_URL = "http://localhost:8000"
    
    # Upload example
    result = upload_file("example.txt", API_URL)
    print(f"Upload result: {result}")
    
    # Get file hash from response
    file_hash = result['metadata']['hash']['sha256']
    
    # Download example
    success = download_file(file_hash, "downloaded_example.txt", API_URL)
    print(f"Download success: {success}")
    
    # List all files
    files = list_files(API_URL)
    print(f"All files: {files}")