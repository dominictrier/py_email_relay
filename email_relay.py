import os
import sys
import datetime
import imaplib
import email
import argparse
import tempfile
import smtplib
import logging

# Suppress SMTP communication logging
logging.getLogger('smtplib').setLevel(logging.CRITICAL)

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
from PyPDF2 import PdfMerger

# Debug logging function
def debug_log(message):
    if os.getenv('DEBUG_EMAIL_RELAY', 'false').lower() == 'true':
        print(message)

# Load environment variables
load_dotenv()

class EmailRelay:
    def __init__(self, simulate=False):
        # Simulation mode
        self.simulate = simulate
        self.simulation_dir = os.path.join(os.path.dirname(__file__), 'email_simulation')
        
        # Create simulation directory if it doesn't exist
        if self.simulate:
            os.makedirs(self.simulation_dir, exist_ok=True)

        # Source Email Configuration (Inbox)
        self.source_host = os.getenv('SOURCE_EMAIL_HOST')
        self.source_port = int(os.getenv('SOURCE_EMAIL_PORT'))
        self.source_username = os.getenv('SOURCE_EMAIL_USERNAME')
        self.source_password = os.getenv('SOURCE_EMAIL_PASSWORD')

        # Relay Email Configuration (SMTP)
        self.relay_host = os.getenv('RELAY_EMAIL_HOST')
        self.relay_port = int(os.getenv('RELAY_EMAIL_PORT'))
        self.relay_username = os.getenv('RELAY_EMAIL_USERNAME')
        self.relay_password = os.getenv('RELAY_EMAIL_PASSWORD')

        # Email Routing Configuration
        self.original_from_email = os.getenv('ORIGINAL_FROM_EMAIL')
        self.relay_from_email = os.getenv('RELAY_FROM_EMAIL')
        self.relay_to_email = os.getenv('RELAY_TO_EMAIL')
        self.invoice_string = os.getenv('INVOICE_STRING', '')

    def fetch_emails(self):
        """Fetch emails from source mailbox"""
        try:
            # Connect to IMAP server
            mail = imaplib.IMAP4_SSL(self.source_host, self.source_port)
            mail.login(self.source_username, self.source_password)
            mail.select('inbox')

            # Search for all emails (not just unseen)
            _, search_data = mail.search(None, 'ALL')
            
            emails = []
            processed_uids = []
            total_emails = len(search_data[0].split())
            unread_emails = 0
            read_emails = 0

            debug_log(f"Total emails in inbox: {total_emails}")

            for num in search_data[0].split():
                # Fetch the email
                _, data = mail.fetch(num, '(RFC822)')
                raw_email = data[0][1]
                email_message = email.message_from_bytes(raw_email)
    
                # Check if email is unread
                _, flags_data = mail.fetch(num, '(FLAGS)')
                flags = flags_data[0].decode()
                
                if '\Seen' not in flags:
                    unread_emails += 1
                    debug_log(f"[UNREAD] Subject: {email_message['Subject']}, From: {email_message['From']}")
                    emails.append(email_message)
                    
                    # Store the UID for later trash move
                    processed_uids.append(num.decode('utf-8'))
                else:
                    read_emails += 1
                    debug_log(f"[READ] Subject: {email_message['Subject']}, From: {email_message['From']}")

            debug_log(f"Email Summary:")
            debug_log(f"Total Emails: {total_emails}")
            debug_log(f"Unread Emails: {unread_emails}")
            debug_log(f"Read Emails: {read_emails}")

            # Move processed emails to trash
            mail.select('inbox')
            for uid in processed_uids:
                # Mark as read and deleted
                mail.store(uid, '+FLAGS', '(\Seen \Deleted)')
                mail.copy(uid, 'Trash')

            # Expunge deleted messages
            mail.expunge()

            mail.close()
            mail.logout()
            return emails

        except Exception as e:
            debug_log(f"Error fetching and processing emails: {e}")
            return []

    def merge_pdfs(self, pdf_paths, pdf_filenames):
        """Merge PDF files with specific ordering logic

        Args:
            pdf_paths (list): List of paths to PDF files to merge
            pdf_filenames (list): List of original filenames corresponding to pdf_paths

        Returns:
            str or None: Path to merged PDF, or None if merging is not possible
        """
        try:
            # If only one PDF, return None to indicate merging should be skipped
            if len(pdf_paths) <= 1:
                debug_log("Only one PDF, skipping PDF merging.")
                return None
            
            # Count invoice PDFs
            invoice_pdf_indices = [i for i, filename in enumerate(pdf_filenames) if self.invoice_string and self.invoice_string in filename]
            
            # If multiple invoice PDFs, skip merging
            if self.invoice_string and len(invoice_pdf_indices) > 1:
                debug_log(f"Multiple {self.invoice_string} PDFs found, skipping merging.")
                return None
            
            # If one invoice PDF exists
            if invoice_pdf_indices:
                invoice_index = invoice_pdf_indices[0]
                invoice_pdf = pdf_paths[invoice_index]
                invoice_filename = pdf_filenames[invoice_index]

                # Separate invoice PDF and other PDFs
                other_pdf_indices = [i for i in range(len(pdf_paths)) if i != invoice_index]
                other_pdf_indices.sort(key=lambda i: pdf_filenames[i])

                # Combine PDFs in desired order
                pdf_order = [invoice_pdf] + [pdf_paths[i] for i in other_pdf_indices]
            else:
                # No invoice PDF, sort all PDFs alphabetically
                sorted_indices = sorted(range(len(pdf_filenames)), key=lambda i: pdf_filenames[i])
                pdf_order = [pdf_paths[i] for i in sorted_indices]
                invoice_filename = pdf_filenames[sorted_indices[0]]

            # Merge PDFs
            merger = PdfMerger()
            for pdf in pdf_order:
                merger.append(pdf)

            # Determine output filename
            output_filename = invoice_filename

            # Create temp_merged_pdfs directory if not exists
            temp_merge_dir = os.path.join(os.path.dirname(__file__), 'temp_merged_pdfs')
            os.makedirs(temp_merge_dir, exist_ok=True)

            # Save merged PDF
            output_path = os.path.join(temp_merge_dir, output_filename)
            merger.write(output_path)
            merger.close()

            return output_path

        except Exception as e:
            debug_log(f"Error merging PDFs: {e}")
            return None

    def relay_email(self, email_message):
        """Relay a single email with modified sender/recipient and attachments"""
        try:
            # Create a new email message
            msg = MIMEMultipart()
            
            # Use the specified sender from configuration
            msg['From'] = self.original_from_email
            msg['To'] = self.relay_to_email
            
            # Preserve original subject
            msg['Subject'] = email_message['Subject'] or 'Relayed Email'
            
            # Add original sender information in headers
            msg['X-Original-Sender'] = email_message.get('From', 'Unknown Sender')
            
            subject = msg['Subject']
            sender = msg['From']
            email_status = 'RELAYED'
            debug_log(f"[{email_status}] Subject: {subject}, From: {sender}, To={msg['To']}")

            # Sanitize subject for folder name
            safe_subject = ''.join(c for c in msg['Subject'] if c.isalnum() or c in [' ', '_', '-']).rstrip()
            
            # Initialize PDF attachments list
            pdf_attachments = []
            debug_log(f"Processing email attachments for: {email_message['Subject']}")

            # Create simulation directory with timestamp and subject
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            self.simulation_dir = os.path.join(os.path.dirname(__file__), 'email_simulation', f'{timestamp}_{safe_subject}')

            # Process PDF attachments
            for part in email_message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                filename = part.get_filename()
                if filename and filename.lower().endswith('.pdf'):
                    # If in simulation mode, save the PDF
                    if self.simulate:
                        os.makedirs(self.simulation_dir, exist_ok=True)

                        # Save original email
                        email_path = os.path.join(self.simulation_dir, 'email.eml')
                        with open(email_path, 'wb') as f:
                            f.write(email_message.as_bytes())

                        # Generate unique filename
                        unique_filename = os.path.join(self.simulation_dir, filename)
                        counter = 1
                        while os.path.exists(unique_filename):
                            name, ext = os.path.splitext(filename)
                            unique_filename = os.path.join(self.simulation_dir, f"{name}_{counter}{ext}")
                            counter += 1

                        # Save PDF
                        with open(unique_filename, 'wb') as f:
                            f.write(part.get_payload(decode=True))

                        debug_log(f"Saved PDF attachment: {unique_filename}")
                        debug_log(f"PDF Filename details: basename={os.path.basename(unique_filename)}, full_path={unique_filename}")

                    # Collect PDF contents for merging
                    pdf_attachments.append(part.get_payload(decode=True))

            debug_log(f"Total PDF attachments found: {len(pdf_attachments)}")

            # Merge PDFs if multiple attachments
            merged_pdf_path = None
            pdf_paths = []
            pdf_filenames = []
            try:
                if len(pdf_attachments) > 1:
                    # Create temporary PDF files for merging with original filenames
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'application' and part.get_content_subtype() == 'pdf':
                            filename = part.get_filename()
                            debug_log(f"DEBUG: Found PDF part. Filename: {filename}, Content type: {part.get_content_type()}")
                            if filename:
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as temp_pdf:
                                    temp_pdf.write(part.get_payload(decode=True))
                                    pdf_paths.append(temp_pdf.name)
                                    pdf_filenames.append(filename)
                                    debug_log(f"DEBUG: Saved temporary PDF: {temp_pdf.name}, Original filename: {filename}")

                    merged_pdf_path = self.merge_pdfs(pdf_paths, pdf_filenames)
            finally:
                # Clean up temporary PDF files
                for pdf_path in pdf_paths:
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)

            # Attach individual PDFs or merged PDF
            if pdf_attachments:
                if merged_pdf_path:
                    # Attach merged PDF
                    with open(merged_pdf_path, 'rb') as f:
                        merged_pdf_content = f.read()
                    merged_part = MIMEApplication(merged_pdf_content, 'pdf')
                    merged_filename = os.path.basename(merged_pdf_path)
                    merged_part.add_header('Content-Disposition', f'attachment; filename="{merged_filename}"')
                    msg.attach(merged_part)
                else:
                    # Attach individual PDFs with original filenames
                    for part in email_message.walk():
                        if part.get_content_maintype() == 'application' and part.get_content_subtype() == 'pdf':
                            filename = part.get_filename() or 'attachment.pdf'
                            pdf_part = MIMEApplication(part.get_payload(decode=True), 'pdf')
                            pdf_part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                            msg.attach(pdf_part)

            # Extract email body with fallback to HTML
            body = ''
            body_type = 'plain'
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
                elif content_type == 'text/html' and not body:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    body_type = 'html'

            # Attach body
            if body:
                msg.attach(MIMEText(body, body_type))

            # Simulation mode: save email, don't send
            if self.simulate:
                return msg

            # Send email via SMTP
            try:
                # Completely suppress SMTP output unless debug mode is on
                if os.getenv('DEBUG_EMAIL_RELAY', 'false').lower() != 'true':
                    # Redirect stdout and stderr to devnull
                    sys.stdout = open(os.devnull, 'w')
                    sys.stderr = open(os.devnull, 'w')
                
                with smtplib.SMTP(self.relay_host, self.relay_port) as server:
                    server.ehlo()  # Identify ourselves to the server
                    server.starttls()  # Start TLS encryption
                    server.ehlo()  # Re-identify after TLS
                    server.login(self.relay_username, self.relay_password)
                    server.sendmail(msg['From'], msg['To'], msg.as_string())
                
                # Restore stdout and stderr if they were redirected
                if os.getenv('DEBUG_EMAIL_RELAY', 'false').lower() != 'true':
                    sys.stdout = sys.__stdout__
                    sys.stderr = sys.__stderr__
                
                debug_log(f"Email sent successfully to {self.relay_to_email}")
            except Exception as smtp_error:
                # Restore stdout and stderr in case of an exception
                if os.getenv('DEBUG_EMAIL_RELAY', 'false').lower() != 'true':
                    sys.stdout = sys.__stdout__
                    sys.stderr = sys.__stderr__
                
                debug_log(f"Detailed SMTP Error: {smtp_error}")
                import traceback
                traceback.print_exc()
                return None

            return msg

        except Exception as e:
            print(f"Error processing email: {e}")
            return None

    def cleanup_directories(self):
        """Clean up temporary and empty simulation directories"""
        try:
            # Remove temp merged PDFs directory
            temp_merge_dir = os.path.join(os.path.dirname(__file__), 'temp_merged_pdfs')
            if os.path.exists(temp_merge_dir):
                import shutil
                shutil.rmtree(temp_merge_dir)
                debug_log(f"Removed temporary merged PDFs directory: {temp_merge_dir}")

            # Remove empty email simulation directory
            if self.simulate:
                if os.path.exists(self.simulation_dir) and not os.listdir(self.simulation_dir):
                    os.rmdir(self.simulation_dir)
                    debug_log(f"Removed empty simulation directory: {self.simulation_dir}")

        except Exception as e:
            debug_log(f"Error during cleanup: {e}")

    def run(self):
        """Main relay process"""
        try:
            # Fetch emails from source mailbox
            emails = self.fetch_emails()

            # Process and relay each email
            for email_message in emails:
                self.relay_email(email_message)

            # Clean up temporary directories
            self.cleanup_directories()

        except Exception as e:
            debug_log(f"Error in relay process: {e}")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Email Relay Service')
    parser.add_argument('--simulate', action='store_true', help='Simulate email relay by saving .eml files')
    args = parser.parse_args()

    # Initialize relay with simulation mode
    relay = EmailRelay(simulate=args.simulate)
    relay.run()

if __name__ == '__main__':
    main()