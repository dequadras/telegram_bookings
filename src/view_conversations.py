import sys
from datetime import datetime
from typing import List, Optional, Tuple

from database import DatabaseManager


def get_user_by_name(db_manager: DatabaseManager, name: str) -> Optional[dict]:
    """
    Search for a user by name (first_name, last_name, or username)

    Args:
        db_manager: DatabaseManager instance
        name: Name to search for

    Returns:
        User dict if found, None otherwise
    """
    query = """
        SELECT telegram_id, username, first_name, last_name
        FROM users
        WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
    """
    search_term = f"%{name}%"

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (search_term, search_term, search_term))
        results = cursor.fetchall()

        if not results:
            return None

        if len(results) == 1:
            # If only one result, return it directly
            row = results[0]
            return {
                "telegram_id": row[0],
                "username": row[1],
                "first_name": row[2],
                "last_name": row[3],
            }
        else:
            # If multiple results, let the user choose
            print("Multiple users found:")
            for i, row in enumerate(results, 1):
                full_name = f"{row[2] or ''} {row[3] or ''}".strip() or "No name"
                print(f"{i}. {full_name} (@{row[1] or 'No username'})")

            while True:
                try:
                    choice = int(input("Enter the number of the user to view (0 to cancel): "))
                    if choice == 0:
                        return None
                    if 1 <= choice <= len(results):
                        row = results[choice - 1]
                        return {
                            "telegram_id": row[0],
                            "username": row[1],
                            "first_name": row[2],
                            "last_name": row[3],
                        }
                    print("Invalid choice. Please try again.")
                except ValueError:
                    print("Please enter a valid number.")


def format_conversation(conversations: List[Tuple]) -> None:
    """
    Format and print conversation history

    Args:
        conversations: List of conversation tuples (message_type, message_text, timestamp)
    """
    if not conversations:
        print("No conversation history found.")
        return

    print("\n" + "=" * 80)
    print("CONVERSATION HISTORY")
    print("=" * 80)

    for message_type, message_text, timestamp_str in conversations:
        # Convert timestamp string to datetime object
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            formatted_time = timestamp_str

        # Format the message type
        if message_type.lower() == "user":
            sender = "👤 USER"
        elif message_type.lower() == "bot":
            sender = "🤖 BOT"
        else:
            sender = f"[{message_type}]"

        print(f"\n{formatted_time} - {sender}:")
        print(f"{message_text}")
        print("-" * 80)


def main():
    """Main function to run the conversation viewer"""
    db_manager = DatabaseManager()

    print("=" * 80)
    print("TELEGRAM BOOKING CONVERSATION VIEWER")
    print("=" * 80)

    # Ask for a name to search
    name = input("\nEnter a name to search (first name, last name, or username): ")
    if not name:
        print("No name provided. Exiting.")
        return

    # Find the user
    user = get_user_by_name(db_manager, name)
    if not user:
        print(f"No users found matching '{name}'.")
        return

    # Display user info
    full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or "No name"
    print(f"\nViewing conversations for: {full_name} (@{user['username'] or 'No username'})")

    # Get conversation history
    try:
        limit = input("Enter the number of messages to display (default: 50): ")
        limit = int(limit) if limit.strip() else 50

        conversations = db_manager.get_conversation_history(user["telegram_id"], limit)
        format_conversation(conversations)

    except Exception as e:
        print(f"Error retrieving conversations: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
